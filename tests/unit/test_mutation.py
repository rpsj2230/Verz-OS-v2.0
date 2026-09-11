"""The harness that verifies every other guard, held to the four ways it went wrong by hand.

Each of these is a failure that actually happened in this repository before the procedure was
a module: a mutant read by a second session, an exit code mistaken for a catch, a table row
produced by a test that was already red, and a mutation that changed nothing.

The expensive tests here really do create a worktree and really do run pytest inside it, and
that is deliberate. The whole claim of this module is about what happens on disk in another
directory, and a mock of `subprocess` would test the arrangement of the calls rather than the
property. They are marked `slow` so a fast loop can skip them and CI cannot.

Task ids: M0.1.6
"""

from __future__ import annotations

import inspect
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from brain.ops.mutation import (
    A_CRASH_IS_NOT_A_CAUGHT_MUTATION,
    NO_BYTECODE,
    Mutation,
    MutationError,
    Report,
    Verdict,
    failures_in,
    verify,
)

REPO = Path(__file__).resolve().parents[2]


def a_mutation(
    *,
    label: str = "a guard stops guarding",
    path: str = "src/brain/ops/mutation.py",
    before: str = "caught=bool(caught),",
    after: str = "caught=True,",
    tests: tuple[str, ...] = ("tests/unit/test_mutation.py",),
) -> Mutation:
    """One valid mutation, with a single field overridden per test.

    Keyword defaults rather than a dict splat. A splat of `dict[str, object]` is a hole mypy
    cannot see through, and this helper's whole job is to build values the constructor is
    about to refuse, so the one place types would catch a slip is the place they were off.
    """
    return Mutation(label=label, path=path, before=before, after=after, tests=tests)


# --- a mutation that cannot be trusted is refused before anything runs ----------------------


def test_a_mutation_that_changes_nothing_cannot_be_constructed() -> None:
    """`before == after` survives every test that exists and reads in the table as a missing
    guard, which is how an afternoon goes into writing a test for a property already held.

    Refused at construction rather than reported in the table, because by the time it is a row
    somebody has already believed it.

    Delete this and a copy-paste slip in a mutation list produces a survivor nobody can
    explain."""
    with pytest.raises(MutationError, match="changes nothing"):
        a_mutation(before="x = 1", after="x = 1")


def test_a_mutation_with_no_tests_watching_it_cannot_be_constructed() -> None:
    """A mutation is a claim that some named test notices. With no tests it is a claim about
    nothing, and it would be recorded as a survivor, which is the same word used for a real
    missing guard.

    Delete this and an empty `tests` tuple produces a table full of survivors and an afternoon
    spent looking for guards that were never asked to fire."""
    with pytest.raises(MutationError, match="names no tests"):
        a_mutation(tests=())


def test_a_mutation_with_no_label_cannot_be_constructed() -> None:
    """The label is the table row, and the table is what goes in the commit message. A blank
    one is a line somebody has to reconstruct from the diff.

    Delete this and the report has a row that says nothing in the column that carries the
    meaning."""
    with pytest.raises(MutationError, match="no label"):
        a_mutation(label="   ")


@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "../outside.py", "src/../../escape.py"],
    ids=["absolute", "parent", "through_the_middle"],
)
def test_a_mutation_pointing_outside_the_repository_cannot_be_constructed(path: str) -> None:
    """The safety argument is that nothing outside the throwaway worktree is touched, and a
    path with `..` in it or an absolute path walks straight out of it.

    Three shapes rather than one, because a check for a leading slash misses `..` and a check
    for a leading `..` misses one in the middle.

    Delete this and the harness can write anywhere the process can, which is everywhere."""
    with pytest.raises(MutationError, match="inside the repository"):
        a_mutation(path=path)


def test_a_mutation_naming_a_real_file_inside_the_tree_is_accepted() -> None:
    """The positive sibling. Four refusals above are all satisfied by a constructor that
    refuses everything, at which point no mutation can be written at all.

    Delete this and the path check can tighten until it rejects ordinary paths, and the only
    symptom is that nobody can use the harness."""
    one = a_mutation()

    assert one.path == "src/brain/ops/mutation.py"
    assert one.tests == ("tests/unit/test_mutation.py",)


# --- a catch is a named failure, never an exit code -----------------------------------------


def test_a_crash_is_not_read_as_a_catch() -> None:
    """**The trap that makes a broken harness report a perfect score.** A mutation that breaks
    an import, a collection or the syntax of the file exits non-zero without a single test
    having an opinion, and it does so for every mutation in the run.

    So `failures_in` is asserted against output that has a non-zero exit written all over it
    and no `FAILED` line: a collection error, an internal error, and a plain summary of errors.

    Delete this and the definition of a catch widens to "something went wrong", which is true
    of a harness that has stopped testing anything at all."""
    crashes = [
        "ERROR tests/unit/test_thing.py - ImportError: cannot import name 'gone'\n"
        "!!!!!! Interrupted: 1 error during collection !!!!!!\n",
        "INTERNALERROR> Traceback (most recent call last):\n",
        "1 error in 0.31s\n",
    ]

    for output in crashes:
        assert failures_in(output) == (), output

    assert "named FAILED line" in A_CRASH_IS_NOT_A_CAUGHT_MUTATION


def test_a_named_failure_is_read_as_a_catch_and_the_name_is_kept() -> None:
    """The positive sibling, and the names matter as much as the count: a mutation caught by
    the test written for it is the practice working, and one caught only by a distant test
    usually means the guard is in the wrong place. A harness that reported "caught" without
    saying by what would hide that.

    Parametrised ids are kept whole, because `[space]` and `[a_second_log_line]` distinguish
    the cases of a parametrised guard and dropping them merges three rows into one.

    Delete this and the report loses the column that makes it worth reading."""
    output = (
        "FAILED tests/unit/test_app.py::test_a_trace_id_is_replaced[space] - AssertionError\n"
        "FAILED tests/unit/test_app.py::test_a_trace_id_is_replaced[a_second_log_line]\n"
        "FAILED tests/invariants/test_guards.py::test_no_validator_returns_its_argument\n"
    )

    assert failures_in(output) == (
        "test_a_trace_id_is_replaced[space]",
        "test_a_trace_id_is_replaced[a_second_log_line]",
        "test_no_validator_returns_its_argument",
    )


def test_the_same_test_failing_twice_is_named_once() -> None:
    """pytest prints a summary line per failure, and a parametrised test that fails on two
    parameters with identical ids, or a rerun, would otherwise appear twice in a row whose
    whole job is to be read at a glance.

    Delete this and a table row grows a repeated name, which reads as two tests catching the
    mutation when it is one."""
    output = "FAILED a.py::test_one\nFAILED b.py::test_one\n"

    assert failures_in(output) == ("test_one",)


def test_a_verdict_prints_its_own_row_and_distinguishes_the_three_outcomes() -> None:
    """Caught, survived and crashed are three different things and the middle one is the only
    one that means "write a test". Collapsing crashed into survived sends somebody looking for
    a missing guard when the file does not import.

    Delete this and the table has two words for three states."""
    caught = Verdict(label="a", caught=True, by=("test_x",))
    survived = Verdict(label="a", caught=False)
    crashed = Verdict(label="a", caught=False, crashed=True)

    assert "caught" in caught.row() and "test_x" in caught.row()
    assert "SURVIVED" in survived.row()
    assert "CRASHED" in crashed.row()


def test_a_report_names_its_survivors_rather_than_counting_them() -> None:
    """CLAUDE.md is explicit that a survivor means a missing test or a genuinely equivalent
    mutation, and that telling them apart needs a reader. A count cannot be read; a list can.

    A crashed mutation counts as a survivor here, deliberately: it was not caught, and a run
    that quietly set it aside would be the harness deciding something it cannot know.

    Delete this and a survivor can be dropped from the table by rounding."""
    report = Report(
        verdicts=(
            Verdict(label="caught one", caught=True, by=("test_x",)),
            Verdict(label="survived one", caught=False),
            Verdict(label="crashed one", caught=False, crashed=True),
        )
    )

    assert [one.label for one in report.survivors] == ["survived one", "crashed one"]
    assert "survived one" in report.table()
    assert "crashed one" in report.table()


def test_an_empty_run_says_so_rather_than_printing_an_empty_table() -> None:
    """A table with no rows above a commit message reads as a run that found nothing wrong.

    Delete this and `table()` on an empty report raises on `max()` of an empty sequence, in
    the one place where the failure lands on somebody writing up work that is already done."""
    assert verify([], repo=REPO).table() == "no mutations were run"


# --- the worktree, which is the whole point -------------------------------------------------
#
# These three really do create a worktree and really do run pytest inside it, which costs about
# twelve seconds each. That is the price of testing the claim rather than the arrangement of
# the calls, and the claim is the only reason this module exists.
#
# They work against a probe pair written into the tree and deleted afterwards rather than
# against this file. Two reasons, and the second was found by trying the obvious thing first.
# A test file that mutates the module it is written in has to reason about which copy is
# running. And the worktree is at a *commit*, so a test carrying itself also needs whatever
# `pyproject.toml` it depends on: the first attempt failed with "'slow' not found in `markers`
# configuration option", because the marker registration was uncommitted. A probe with no
# markers and no imports outside the standard library depends on nothing that could be
# uncommitted.


#: Both halves of the probe live under `.scratch`, and that is not tidiness.
#:
#: This pair is the only thing in the repository that writes files into the working tree, and
#: for three days it wrote them where every other run would find them: the source under
#: `src/brain/ops`, the test under `tests/unit`. Both are deleted by the `finally` below, which
#: is correct for the run that wrote them and wrong for every other run, because several
#: sessions work on this repository at once.
#:
#: **The failure it produced was the least diagnosable this repository has made, and it takes
#: two forms.** A bare `pytest` collects `testpaths = ["tests"]`, so a second session picks the
#: probe test up and then loses it mid-run. And roughly twenty checks walk `src/brain` by
#: listing files and then opening them, so a source file that disappears between the listing
#: and the open raises `FileNotFoundError` inside a check that has no opinion about it. Three
#: sessions on three consecutive days spent time on these, each time on a module that was gone
#: before anybody could look at it, and each time it read as a defect in their own change.
#:
#: Skipping the name in each walker was the first fix and it is the wrong one: there are about
#: twenty of them, a skip has to be remembered by everybody who writes the next one, and a
#: check that skips a file is a check with a documented way round it. Moving the files is the
#: fix, because `.scratch` is outside `testpaths` and inside `.gitignore`, so no bare run
#: reaches them and no run of this test dirties the tree.
#:
#: What makes it work, measured rather than assumed: pytest collects a file it is handed by
#: name whatever `norecursedirs` says, and `prepend` import mode puts a test file's own
#: directory on `sys.path`, so the test imports the source beside it as a top-level module
#: rather than through `brain.ops`. `verify` copies carried files by relative path and creates
#: parent directories, so both arrive in the worktree where the test expects them.
PROBE_SOURCE = Path(".scratch/_probe_for_test_mutation.py")
PROBE_TEST = Path(".scratch/test__probe_for_test_mutation.py")


@pytest.fixture
def probe() -> Iterator[None]:
    """A source file with one guard in it, and a test that watches that guard.

    Deleted in `finally`, because a probe left behind is collected by every later run and
    `ruff` has an opinion about it.
    """
    (REPO / PROBE_TEST).parent.mkdir(parents=True, exist_ok=True)
    (REPO / PROBE_SOURCE).write_text(
        '"""A probe written and removed by test_mutation. Task ids: none"""\n\n\n'
        "def loud(value: int) -> int:\n"
        "    if value < 0:\n"
        '        raise ValueError("negative")\n'
        "    return value\n",
        encoding="utf-8",
        newline="\n",
    )
    (REPO / PROBE_TEST).write_text(
        '"""Watches the probe. Written and removed by test_mutation. Task ids: none"""\n\n'
        "import pytest\n\n"
        "from _probe_for_test_mutation import loud\n\n\n"
        "def test_a_negative_value_is_refused() -> None:\n"
        '    """Delete this and the probe has no guard, which is the point of the probe."""\n'
        '    with pytest.raises(ValueError, match="negative"):\n'
        "        loud(-1)\n",
        encoding="utf-8",
        newline="\n",
    )
    try:
        yield
    finally:
        (REPO / PROBE_SOURCE).unlink(missing_ok=True)
        (REPO / PROBE_TEST).unlink(missing_ok=True)


def abandoned_worktrees() -> list[str]:
    """Harness worktrees registered against a directory that is no longer there.

    **Not "every harness worktree", and the difference is what makes this test usable.** The
    first version compared the whole list before and after, which fails whenever another
    session is running its own mutations at the same moment: theirs appears between the two
    reads and is counted as ours. This repository is worked on by several sessions at once, so
    that is not a rare race, and a flaky test in the module whose whole job is to be believed
    is worse than no test.

    A live worktree belonging to somebody else is not a hazard. What breaks the next run is a
    registry entry whose directory is gone, which is exactly what a failed run that skipped
    its cleanup leaves behind, and it is the thing `git worktree add` has an opinion about.
    """
    listed = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    found: list[str] = []
    for line in listed.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        path = line.removeprefix("worktree ").strip()
        if "brain-mutate-" in path and not Path(path).is_dir():
            found.append(path)
    return found


@pytest.mark.slow
@pytest.mark.usefixtures("probe")
def test_a_mutation_runs_in_a_worktree_and_never_touches_the_file_it_names() -> None:
    """**The failure this module was written for, and it was not a testing failure.** One
    session wrote a broken `ops/telemetry.py`, ran pytest and restored it, which is the
    procedure working. A second session read the file inside that window, concluded a stray
    line had survived a commit, and wrote a test saying so. Both behaved correctly.

    So this asserts the real property on real disk: the named file's bytes are identical before
    and after, and the run reports a catch by the named test, which is how we know it was
    genuinely mutated somewhere rather than skipped.

    Not a mock of `subprocess`. A mock would assert the arrangement of the calls, and the claim
    is about a file in another directory.

    Delete this and the harness can quietly mutate in place, which is the state that cost two
    sessions an afternoon and put a false paragraph in a commit message."""
    before = (REPO / PROBE_SOURCE).read_bytes()

    report = verify(
        [
            Mutation(
                label="the probe stops refusing a negative value",
                path=str(PROBE_SOURCE).replace("\\", "/"),
                before="    if value < 0:",
                after="    if False:",
                tests=(str(PROBE_TEST).replace("\\", "/"),),
            )
        ],
        repo=REPO,
        carry=(str(PROBE_TEST).replace("\\", "/"),),
    )

    assert (REPO / PROBE_SOURCE).read_bytes() == before
    assert report.verdicts[0].caught, report.table()
    assert report.verdicts[0].by == ("test_a_negative_value_is_refused",)
    assert report.survivors == ()


@pytest.mark.slow
@pytest.mark.usefixtures("probe")
def test_a_mutation_whose_text_is_not_in_the_file_stops_the_run_and_cleans_up() -> None:
    """A `before` matching nothing has been overtaken by an edit; one matching twice breaks a
    line nobody chose. Both would otherwise produce a survivor, and a survivor is the word for
    a missing guard.

    The whole run stops rather than the row being skipped, because a table missing a row looks
    exactly like a table written that way.

    The cleanup is asserted here rather than in a test of its own because it is the same
    twelve-second worktree: a run that raises must still leave nothing behind, or the failure
    lands on the next person through `git worktree add` rather than on whoever caused it.
    Asserted through `git worktree list`, which is the record `add` consults, rather than by
    looking for a directory.

    Delete this and a stale mutation list reports present guards as absent, and a failed run
    poisons every run after it."""
    before = abandoned_worktrees()

    with pytest.raises(MutationError, match="matches 0 places"):
        verify(
            [
                Mutation(
                    label="text that is not in the probe",
                    path=str(PROBE_SOURCE).replace("\\", "/"),
                    before="this string is certainly not in the probe",
                    after="nor is this one",
                    tests=(str(PROBE_TEST).replace("\\", "/"),),
                )
            ],
            repo=REPO,
            carry=(str(PROBE_TEST).replace("\\", "/"),),
        )

    assert abandoned_worktrees() == before


@pytest.mark.slow
@pytest.mark.usefixtures("probe")
def test_a_run_whose_tests_were_already_failing_is_refused_rather_than_reported() -> None:
    """**One contaminated row is worse than no table.** A named test that fails before the
    mutation fails after it, and the row says caught by a test that was never watching. The
    table is what gets quoted in the commit message, and nobody re-derives it.

    Provoked by breaking the probe's guard *before* the run, so the baseline is genuinely red
    rather than made red by the harness itself. That is the real shape of the mistake: somebody
    runs a mutation table on a tree that is already failing.

    Delete this and a mutation table can be produced against a broken tree, which is precisely
    when somebody is most likely to be running one."""
    (REPO / PROBE_SOURCE).write_text(
        '"""A probe written and removed by test_mutation. Task ids: none"""\n\n\n'
        "def loud(value: int) -> int:\n"
        "    return value\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(MutationError, match="fail before any mutation"):
        verify(
            [
                Mutation(
                    label="anything at all, because nothing gets this far",
                    path=str(PROBE_SOURCE).replace("\\", "/"),
                    before="    return value",
                    after="    return value + 1",
                    tests=(str(PROBE_TEST).replace("\\", "/"),),
                )
            ],
            repo=REPO,
            carry=(str(PROBE_TEST).replace("\\", "/"),),
        )


def test_the_worked_example_in_claude_md_names_code_that_exists() -> None:
    """**Written because the first version of that example did not.** It named
    `src/brain/core/entitlement.py`, a line `if not scope.predicate:` and a
    `tests/unit/test_entitlement.py`, and not one of the three existed. An example that cannot
    be run is worse than no example: it is a promise that costs whoever tries it the time to
    work out that the file is missing rather than that they have misunderstood.

    Checked as the harness itself checks a mutation, which is the same property from the other
    side: the file exists, the test file exists, and the `before` text appears exactly once.
    Zero means the code moved underneath the documentation; twice means the example would break
    a line nobody chose.

    Delete this and the example rots the first time anybody renames a function, silently,
    because documentation has no tests unless somebody writes them."""
    guidance = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    block = guidance[guidance.index("from brain.ops.mutation import") :]
    block = block[: block.index("```")]

    quoted = dict(re.findall(r'(\w+)="([^"]*)"', block))
    watched = re.search(r'tests=\(\s*"([^"]*)"', block)

    assert watched is not None, "the example no longer passes a tests tuple"
    named = REPO / quoted["path"]
    watching = REPO / watched.group(1)

    assert named.is_file(), f"CLAUDE.md's example names {quoted['path']}, which does not exist"
    assert watching.is_file(), f"and {watched.group(1)}, which does not exist either"
    assert named.read_text(encoding="utf-8").count(quoted["before"]) == 1


def test_the_harness_has_no_parameter_naming_where_the_work_happens() -> None:
    """**The design, asserted rather than described.** A harness that accepts a directory is a
    harness somebody points at the repository on the day they are in a hurry, and the docstring
    saying not to is the thing that did not work.

    Over the signature rather than the prose, because a parameter called `cwd` or `workspace`
    or `tree` is the same hole whatever it is called.

    Delete this and "takes a throwaway worktree by construction" becomes "takes a throwaway
    worktree by convention", which is what the leaf was written to rule out."""
    names = set(inspect.signature(verify).parameters)

    assert names == {"mutations", "repo", "commit", "carry"}
    assert not any(one in names for one in ("cwd", "workspace", "tree", "directory", "target"))


def test_bytecode_writing_is_switched_off_for_every_run() -> None:
    """Back-to-back writes to one file let pytest import a stale `.pyc`, which produces false
    survivals. It cannot produce a false catch, so earlier work stays sound, and it sends
    somebody hunting for a guard that is already there.

    Asserted as the value the environment actually gets rather than as a comment, because this
    is one line that is easy to lose in a refactor of the subprocess call.

    Delete this and a fast run reports survivors a slow one does not, which reads as flakiness
    rather than as caching."""
    assert NO_BYTECODE == {"PYTHONDONTWRITEBYTECODE": "1"}

    source = (REPO / "src" / "brain" / "ops" / "mutation.py").read_text(encoding="utf-8")
    assert "env={**os.environ, **NO_BYTECODE}" in source


def test_a_test_that_prints_outside_the_platform_encoding_does_not_crash_the_reader() -> None:
    """**The harness exists to be believed, and it was crashing on the tests of any module
    that prints non-ASCII.** `text=True` alone decodes with the platform encoding, which on
    this machine is a Windows code page. `brain.locale`'s tests print the Chinese in its own
    catalogue, and that produced a `UnicodeDecodeError` in the reader thread and then
    `TypeError: expected string or bytes-like object, got 'NoneType'` in `failures_in`,
    because `stdout` came back as None.

    That is the worst available failure mode here. A crash with no message about encoding
    reads as the mutation crashing rather than the reader, which is exactly the distinction
    `A_CRASH_IS_NOT_A_CAUGHT_MUTATION` exists to keep, and it arrived in the one module every
    other module's evidence rests on.

    Asserted on the call rather than by running a mutation over a module that prints Chinese,
    which would make this test depend on such a module continuing to exist. Both keywords are
    checked, because either alone is not the fix: without `errors="replace"` a byte the
    harness cannot decode still raises, and a raise here loses a `FAILED` line that is plain
    ASCII either side of it.

    **Read off the parsed call and not off the source text**, which the first version of this
    got wrong and which is the trap `CLAUDE.md` names: the paragraph explaining why `text=True`
    is not enough contains the string `text=True`, so a substring check over the function body
    was satisfied by its own comment. Two tests in this repository have already been satisfied
    by their own docstrings.

    Delete this and the harness goes back to decoding at whatever the machine happens to be
    set to, and the failure it produces names neither the encoding nor the reader."""
    import ast
    import inspect
    import textwrap

    from brain.ops import mutation

    tree = ast.parse(textwrap.dedent(inspect.getsource(mutation._run_tests)))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "subprocess.run"
    ]

    assert len(calls) == 1, "the runner no longer makes exactly one subprocess call"
    passed = {one.arg: ast.unparse(one.value) for one in calls[0].keywords if one.arg}

    assert passed.get("encoding") == "'utf-8'"
    assert passed.get("errors") == "'replace'"
    assert "text" not in passed, "text=True decodes at the platform encoding"


def test_neither_half_of_the_probe_is_written_where_another_run_would_read_it() -> None:
    """**The probe pair is the only thing in this repository that writes files into the working
    tree, and for three days it wrote both of them where every other run would find them.**

    Two areas, because the pair had two separate ways of breaking a stranger's run.

    `testpaths` is what a bare `pytest` collects when given no arguments, so a probe test
    written inside it is collected by any session that starts a run while the fixture holds and
    then deleted from under that run by the `finally`. And `brain.ops.independence.SEARCHED`
    names the areas this repository's own checks walk, which they do by listing files and then
    opening them: a source file that vanishes between the listing and the open raises
    `FileNotFoundError` inside a check that has no opinion about it. That second one is not
    hypothetical. It arrived as
    `test_the_import_graph_is_read_once_and_handed_out_unchangeable` failing with
    `FileNotFoundError: src/brain/ops/_probe_for_test_mutation.py` in a session doing unrelated
    work, and it is the third day in a row this pair cost somebody time.

    Both sets are read out of their declarations rather than restated here, because a test that
    compares a constant against its own copy is green for every value either could hold: this
    repository has been caught by exactly that three times in one afternoon. So widening
    `testpaths` to cover `.scratch`, adding `.scratch` to the searched areas, or moving either
    half back where it was, all turn this red.

    Delete this and the pair drifts back into `src/brain` and `tests/unit` on the first
    tidy-up, and the next session to lose a day to it has no record that it was understood."""
    import tomllib

    from brain.ops.independence import SEARCHED

    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    collected = config["tool"]["pytest"]["ini_options"]["testpaths"]

    assert collected, "with no testpaths a bare run collects the rootdir and this cannot hold"
    assert SEARCHED, "with no searched areas the second half of this claim is about nothing"

    for half in (PROBE_SOURCE, PROBE_TEST):
        for area in collected:
            assert not half.is_relative_to(area), (
                f"{half} is inside testpaths {area}, so a concurrent bare run collects it"
            )
        for area in SEARCHED:
            assert not half.is_relative_to(area), (
                f"{half} is inside the searched area {area}, so a check walking it can open a "
                f"file this fixture is about to delete"
            )
