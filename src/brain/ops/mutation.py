"""The mutation harness, as a module that cannot break a file another session is reading.

Every guard in this repository is supposed to be verified by mutation: break it, watch the
named test fail, restore it byte-identically. CLAUDE.md argues for the practice at length and
the practice has been carried out by hand, in a shell, dozens of times. This is that procedure
written once, because carrying it out by hand went wrong four separate ways and three of them
are silent.

**The worst of the four is why this exists at all, and it is not a testing failure.** On
2026-09-07 one session wrote a deliberately broken `ops/telemetry.py`, ran pytest and restored
it, which is the procedure working exactly as intended. A second session read that file inside
the window, saw the mutant, correctly concluded that a stray line had appeared after the
commit, and wrote a test whose docstring recorded the discovery. Both sessions behaved
correctly. The tree ended up with a test asserting a property that had never been broken and a
commit message explaining a defect that did not exist.

So the mutation never touches the working tree. `verify` creates a throwaway `git worktree` at
a chosen commit, copies in the files under test, mutates *there*, and removes it afterwards.
There is no parameter for a directory, and that absence is the design: a harness that accepts
one is a harness somebody points at the repository on the day they are in a hurry.

**The other three traps, each of which produced a wrong answer here before this module.**

*A non-zero exit is not a catch.* A mutation that breaks an import, a collection error, a
syntax error and a genuine failure all exit non-zero, and only the last is evidence. Worse,
the first three exit non-zero for **every** mutation, so a broken harness reports a perfect
score. `Verdict.caught` is true only when the output carries a `FAILED <path>::<name>` line,
and `Verdict.by` names which tests, so the report can be read against the tests that were
supposed to catch it rather than against a count.

*A baseline that was already red.* If a named test fails before the mutation, it fails after
it, and the mutation is recorded as caught by a test that was never watching. `verify` runs
the tests unmutated first and refuses the whole run if any fail, because one contaminated row
in a table of thirty is worse than no table: the table is what gets quoted in the commit
message.

*A mutation that changes nothing.* `before == after`, or a `before` that does not appear, or
one that appears twice and is replaced in the wrong place. All three survive every test and
read as a missing guard, which is how an afternoon goes into writing a test for a property
that is already held. `Mutation` refuses the first at construction and `verify` refuses the
other two before running anything.

**What this deliberately does not do.** It does not generate mutations. Every mutation here is
written by somebody who decided which guard they were attacking, because the value of the
practice is the argument about what could go wrong rather than the arithmetic of a score. A
generator produces a survival rate, and a survival rate is a number people optimise.

It also does not judge a survivor. CLAUDE.md is explicit that a survivor means either a
missing test or a genuinely equivalent mutation, and telling the two apart needs a reader.
`Verdict` reports what happened and says nothing about what it means.

Task ids: M0.1.6
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

#: A pytest failure line, which is the only evidence that counts as a catch.
#:
#: `FAILED tests/unit/test_thing.py::test_a_property - AssertionError: ...`. The name is what
#: makes the report readable: a mutation caught by the test written for it is the practice
#: working, and one caught only by a distant test usually means the guard is in the wrong
#: place.
FAILED_LINE = re.compile(r"^FAILED\s+(?P<path>\S+?)::(?P<name>[^\s\[]+(?:\[[^\]]*\])?)", re.M)

#: Why a non-zero exit code is not evidence.
A_CRASH_IS_NOT_A_CAUGHT_MUTATION = (
    "A mutation that breaks an import, a collection or the syntax of the file exits non-zero "
    "without a single test having an opinion, and it does so for every mutation in the run, "
    "so a harness that counts exit codes reports a perfect score at exactly the moment it has "
    "stopped testing anything. A catch is a named FAILED line and nothing else."
)

#: Why the tests are run before they are trusted.
A_TEST_THAT_WAS_ALREADY_RED_CATCHES_EVERYTHING = (
    "A named test that fails before the mutation fails after it, and the row says caught. One "
    "contaminated row in a table of thirty is worse than no table at all, because the table is "
    "what gets quoted in the commit message and nobody re-derives it."
)

#: Why the harness owns the directory rather than accepting one.
A_HARNESS_THAT_TAKES_A_DIRECTORY_IS_POINTED_AT_THE_REPOSITORY = (
    "On 2026-09-07 one session's mutant was read by another session, which concluded a stray "
    "line had survived a commit and wrote a test saying so. Both were behaving correctly. The "
    "fix is not a warning in a docstring: it is that there is no parameter to misuse."
)

#: Bytecode written by one run is imported by the next, so a file mutated and restored inside
#: a second can be tested against a stale `.pyc`. It produces false survivals only, never
#: false catches, which makes it the kind of error that leaves earlier work sound and sends
#: somebody hunting for a guard that is already there.
NO_BYTECODE = {"PYTHONDONTWRITEBYTECODE": "1"}


class MutationError(Exception):
    """Raised when the harness cannot make a claim it would stand behind."""


@dataclass(frozen=True)
class Mutation:
    """One deliberate break, and the tests that are supposed to notice.

    `before` and `after` are text rather than a line number, because a line number is wrong
    the moment anybody edits above it and wrong silently: the harness would cheerfully break
    a different line and report the result under this label.
    """

    #: What is being broken, in words, as it will appear in the table.
    label: str
    #: Repo-relative path of the file to mutate.
    path: str
    #: The exact text to replace. Must appear exactly once in the file.
    before: str
    #: What to put in its place.
    after: str
    #: Test files or node ids to run. Narrow is better: a mutation run against the whole
    #: suite takes minutes and tells you less, because the point is which test catches it.
    tests: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.label.strip():
            msg = "a mutation with no label produces a table row nobody can read"
            raise MutationError(msg)
        if self.before == self.after:
            msg = (
                f"{self.label!r} changes nothing, so it survives every test that exists and "
                "reads in the table as a missing guard"
            )
            raise MutationError(msg)
        if not self.tests:
            msg = (
                f"{self.label!r} names no tests, and a mutation nothing is watching is not a "
                "test of anything"
            )
            raise MutationError(msg)
        candidate = PurePosixPath(self.path.replace("\\", "/"))
        # `is_absolute()` alone is not enough and the gap is platform-shaped: on Windows a
        # path beginning `/` is drive-relative rather than absolute, so `/etc/passwd` answers
        # False there and True on the machine that runs CI. A rule that holds on one operating
        # system and not the other is the worst kind for a safety check, because it passes
        # locally.
        escapes = (
            candidate.is_absolute()
            or self.path.startswith(("/", "\\"))
            or ".." in candidate.parts
            or (len(self.path) > 1 and self.path[1] == ":")
        )
        if escapes:
            msg = (
                f"{self.path!r} is not a path inside the repository, and the whole safety "
                "argument here is that nothing outside the throwaway worktree is touched"
            )
            raise MutationError(msg)


@dataclass(frozen=True)
class Verdict:
    """What happened to one mutation. Reports, and does not interpret.

    A survivor means a missing test or a genuinely equivalent mutation, and nothing here can
    tell those apart. Both outcomes are legitimate and both belong in the commit message; what
    must not happen is a survivor quietly leaving the table.
    """

    label: str
    #: True only when a named test failed. See `A_CRASH_IS_NOT_A_CAUGHT_MUTATION`.
    caught: bool
    #: The tests that failed, named, in the order pytest reported them.
    by: tuple[str, ...] = ()
    #: Set when the run produced no named failure and no clean pass: an import broke, or
    #: collection did. Not a catch, and worth seeing rather than scoring.
    crashed: bool = False
    #: The tail of what pytest printed, kept only for a crash.
    #:
    #: **Added because a crashed verdict with nothing attached is a dead end.** The row says
    #: the mutation did not compile or did not import and gives you no way to find out which,
    #: in a worktree that has already been removed. A caught or surviving mutation needs no
    #: output: the named tests are the answer in one case and the absence of them in the other.
    output: str = ""

    def row(self, width: int = 0) -> str:
        """One line of the table, for a commit message."""
        verdict = "caught" if self.caught else ("CRASHED" if self.crashed else "SURVIVED")
        return f"{self.label:<{width}} | {verdict:<9} | {', '.join(self.by)}".rstrip()


@dataclass(frozen=True)
class Report:
    """Every verdict, and the digests proving the files came back unchanged."""

    verdicts: tuple[Verdict, ...]
    #: Repo-relative path to the md5 of each file as it was before anything was mutated.
    baselines: dict[str, str] = field(default_factory=dict)

    @property
    def survivors(self) -> tuple[Verdict, ...]:
        return tuple(one for one in self.verdicts if not one.caught)

    def table(self) -> str:
        """The whole table, formatted for pasting into a commit message."""
        if not self.verdicts:
            return "no mutations were run"
        width = max(len(one.label) for one in self.verdicts)
        return "\n".join(one.row(width) for one in self.verdicts)


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  arguments are literals or paths from this module
        ["git", *args],  # noqa: S607  git on PATH, as everywhere else in this repo
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _digest(path: Path) -> str:
    return hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()


def _run_tests(tests: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  arguments come from a Mutation, which validates them
        ["uv", "run", "pytest", *tests, "--no-header", "--disable-warnings"],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **NO_BYTECODE},
    )


def failures_in(output: str) -> tuple[str, ...]:
    """The named tests that failed, from pytest's own summary lines.

    Exposed rather than private because it is the whole definition of a catch, and a
    definition that cannot be tested directly is one that gets quietly widened. See
    `A_CRASH_IS_NOT_A_CAUGHT_MUTATION`.
    """
    return tuple(dict.fromkeys(match.group("name") for match in FAILED_LINE.finditer(output)))


def verify(
    mutations: Iterable[Mutation],
    *,
    repo: Path,
    commit: str = "HEAD",
    carry: Iterable[str] = (),
) -> Report:
    """Run every mutation in a throwaway worktree and report what caught each one.

    `carry` names files to copy from the working tree into the worktree before anything runs,
    which is how work that is not committed yet gets tested. Every path a mutation names is
    carried automatically; name a file here only when it is needed and not mutated, which in
    practice means the test file.

    There is no parameter for where the work happens. See
    `A_HARNESS_THAT_TAKES_A_DIRECTORY_IS_POINTED_AT_THE_REPOSITORY`.
    """
    planned = list(mutations)
    if not planned:
        return Report(verdicts=())

    carried = {one.path for one in planned} | set(carry)
    workspace = Path(tempfile.gettempdir()) / f"brain-mutate-{uuid.uuid4().hex[:12]}"

    added = _git("worktree", "add", "--quiet", "--detach", str(workspace), commit, cwd=repo)
    if added.returncode != 0:
        msg = f"could not create a worktree at {commit}: {added.stderr.strip()}"
        raise MutationError(msg)

    try:
        for name in sorted(carried):
            source = repo / name
            if not source.is_file():
                msg = f"{name} is not a file in {repo}, so there is nothing to carry or mutate"
                raise MutationError(msg)
            target = workspace / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

        baselines = {name: _digest(workspace / name) for name in sorted(carried)}

        # The baseline run, before anything is broken. See
        # `A_TEST_THAT_WAS_ALREADY_RED_CATCHES_EVERYTHING`. Every named test across every
        # mutation at once, because a test red for one mutation is red for all of them and
        # running them per mutation would pay for the same answer repeatedly.
        every_test = sorted({one for mutation in planned for one in mutation.tests})
        clean = _run_tests(every_test, cwd=workspace)
        if failures_in(clean.stdout):
            msg = (
                "these tests fail before any mutation, so every row in the table would be "
                f"evidence about nothing: {', '.join(failures_in(clean.stdout))}"
            )
            raise MutationError(msg)
        if clean.returncode != 0:
            # Both streams, because the first version printed stdout alone and a collection
            # error writes to stderr: the message came out as the sentence below with nothing
            # after it, which is a diagnostic saying only that a diagnostic exists.
            msg = (
                "the unmutated tests did not run cleanly, so nothing below would be evidence"
                f"\n--- stdout\n{clean.stdout[-2000:]}\n--- stderr\n{clean.stderr[-2000:]}"
            )
            raise MutationError(msg)

        verdicts: list[Verdict] = []
        for mutation in planned:
            target = workspace / mutation.path
            original = target.read_bytes()
            text = original.decode("utf-8")
            found = text.count(mutation.before)
            if found != 1:
                msg = (
                    f"{mutation.label!r} matches {found} places in {mutation.path}; a mutation "
                    "that matches none has been overtaken by an edit and one that matches "
                    "several breaks a line nobody chose"
                )
                raise MutationError(msg)

            target.write_bytes(text.replace(mutation.before, mutation.after).encode("utf-8"))
            run = _run_tests(mutation.tests, cwd=workspace)
            target.write_bytes(original)
            if _digest(target) != baselines[mutation.path]:
                msg = f"{mutation.path} did not come back byte-identical after {mutation.label!r}"
                raise MutationError(msg)

            caught = failures_in(run.stdout)
            verdicts.append(
                Verdict(
                    label=mutation.label,
                    caught=bool(caught),
                    by=caught,
                    crashed=not caught and run.returncode != 0,
                    output=(
                        ""
                        if caught or run.returncode == 0
                        else run.stdout[-1500:] + "\n" + run.stderr[-500:]
                    ),
                )
            )
        return Report(verdicts=tuple(verdicts), baselines=baselines)
    finally:
        # Forced, and pruned afterwards, because a worktree left behind by a failed run is a
        # directory the next run's `git worktree add` has an opinion about.
        _git("worktree", "remove", "--force", str(workspace), cwd=repo)
        _git("worktree", "prune", cwd=repo)
