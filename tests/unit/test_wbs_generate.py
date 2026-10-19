"""The work breakdown's generated files are made on use and never committed.

Task ids: none
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from brain import status
from brain.ops import sweeps, wbs_generate
from brain.ops.wbs_generate import (
    COMMAND,
    GENERATED,
    GeneratedFileMissing,
    GeneratedFilesError,
    generate,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A repository holding the real sources and none of their output."""
    shutil.copytree(ROOT / "docs" / "wbs", tmp_path / "docs" / "wbs")
    return tmp_path


def test_the_three_files_are_made_from_the_sources_and_are_what_a_reader_expects(
    checkout: Path,
) -> None:
    """The positive case, held first so that every refusal below is a refusal of something that
    otherwise works. The files are read back the way their readers read them.

    Delete this and a generator that writes empty files satisfies every other test here."""
    changed = generate(checkout)

    assert changed == GENERATED
    docs = checkout / "docs"
    plan = status.load_wbs(docs / "wbs.json")
    assert len(plan["modules"]) > 10
    assert sum(len(one["leaf_ids"]) for one in plan["modules"]) > 1000
    tracker = (docs / "tracker.html").read_text(encoding="utf-8")
    assert "<title>" in tracker
    assert "</script>" in tracker
    windows = json.loads((docs / "wave-windows.json").read_text(encoding="utf-8"))["windows"]
    assert "0" in windows
    leftovers = [one.name for one in docs.iterdir() if one.name.startswith(".")]
    assert leftovers == [], "a staging file was left behind after the rename"


def test_generating_in_a_scratch_directory_gives_the_bytes_node_gives_in_place(
    checkout: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The scripts write beside themselves, so the design runs them in a copy and moves the
    output. That is only safe if the location changes nothing they write, and a path or a clock
    leaking into the output would make the moved file differ from the one a developer got by
    running node by hand, which is the command the older documents tell people to run.

    Delete this and the two ways of generating can drift apart unseen."""
    in_place = tmp_path_factory.mktemp("in-place")
    shutil.copytree(ROOT / "docs" / "wbs", in_place / "docs" / "wbs")
    node = wbs_generate.find_node()
    for script in wbs_generate.SCRIPTS:
        subprocess.run([node, str(in_place / "docs" / "wbs" / script)], cwd=in_place, check=True)

    generate(checkout)

    for name in GENERATED:
        assert (checkout / "docs" / name).read_bytes() == (in_place / "docs" / name).read_bytes()


def test_unchanged_output_is_not_rewritten_and_a_stale_file_is_replaced(checkout: Path) -> None:
    """A second run reports nothing changed and leaves the file's modification time alone, so a
    reader never sees a rewrite it did not need; a file that differs is put right and named.

    Delete this and every pytest session rewrites three files that another process may be
    reading, which is the race the rename exists to avoid."""
    generate(checkout)
    target = checkout / "docs" / "wbs.json"
    before = target.stat().st_mtime_ns

    assert generate(checkout) == ()
    assert target.stat().st_mtime_ns == before

    target.write_text("{}", encoding="utf-8")
    assert generate(checkout) == ("wbs.json",)
    assert len(status.load_wbs(target)["modules"]) > 10


def test_a_leaf_the_sources_name_that_does_not_exist_stops_generation_and_changes_nothing(
    checkout: Path,
) -> None:
    """This is what the old `Tracker matches the WBS` job was for, kept: an id in `progress.js`
    that names no leaf makes the generator refuse, and the files already there are not replaced
    by half of a run. The message names the script and the id, so the sentence a person reads is
    the reason and not a stack.

    Delete this and CI stops failing on a sources-and-generator disagreement, because the files
    it used to diff are no longer committed to disagree with."""
    generate(checkout)
    good = {name: (checkout / "docs" / name).read_bytes() for name in GENERATED}
    progress = checkout / "docs" / "wbs" / "progress.js"
    text = progress.read_text(encoding="utf-8")
    marker = "const PROGRESS = {\n"
    assert marker in text
    # Assembled at run time: the traceability sweep reads this file as evidence, and a literal id
    # here would count as a test naming it.
    unknown = "M" + "999.9.9"
    progress.write_text(
        text.replace(
            marker, marker + f'  "{unknown}": {{status: "OPEN", updated: "2026-01-01"}},\n', 1
        ),
        encoding="utf-8",
    )

    with pytest.raises(GeneratedFilesError) as refused:
        generate(checkout)

    assert "export.js" in str(refused.value)
    assert unknown in str(refused.value)
    assert {name: (checkout / "docs" / name).read_bytes() for name in GENERATED} == good


def test_a_script_that_never_finishes_is_a_sentence_not_a_hung_build(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a hung node holds a CI job until the runner's own limit."""

    def never(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="node", timeout=1)

    monkeypatch.setattr(subprocess, "run", never)

    with pytest.raises(GeneratedFilesError, match="did not finish"):
        generate(checkout)


def test_a_machine_without_node_is_told_what_to_install_and_what_to_run(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sentence a new developer meets first, so it names the tool, how to get it and the
    command to run afterwards.

    Delete this and the failure becomes a bare `FileNotFoundError` from deep in a subprocess
    call, which tells nobody that the cause is a missing runtime."""
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(wbs_generate, "FALLBACK_NODE", ())

    with pytest.raises(GeneratedFilesError) as refused:
        generate(checkout)

    assert "node was not found" in str(refused.value)
    assert COMMAND in str(refused.value)


def test_sources_that_are_not_there_are_a_refusal_not_an_empty_plan(tmp_path: Path) -> None:
    """Delete this and a directory with no `docs/wbs` generates nothing and reports success."""
    with pytest.raises(GeneratedFilesError, match="nothing to generate"):
        generate(tmp_path)
    assert not (tmp_path / "docs" / "wbs.json").exists()


def test_a_reader_asked_for_a_file_nobody_generated_gets_one_sentence_naming_the_command(
    tmp_path: Path,
) -> None:
    """`load_wbs` is every reader's door. The refusal is also a `FileNotFoundError`, so a caller
    that already treats an absent file as absent still does; a file that is not one of the
    generated three keeps the error it always had.

    Delete this and an absent plan reads as an unhelpful traceback, or worse, as an empty one."""
    absent = tmp_path / "wbs.json"
    with pytest.raises(GeneratedFileMissing) as refused:
        status.load_wbs(absent)
    assert isinstance(refused.value, FileNotFoundError)
    assert COMMAND in str(refused.value)
    assert "not committed" in str(refused.value)

    other = tmp_path / "plan.json"
    assert wbs_generate.require(other) == other
    with pytest.raises(FileNotFoundError) as plain:
        status.load_wbs(other)
    assert not isinstance(plain.value, GeneratedFileMissing)


def test_the_traceability_helpers_raise_when_the_plan_cannot_be_made_and_answer_when_it_can(
    checkout: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """They answer an unreadable repository with an empty result, which is right for a missing
    history and wrong for a missing plan: `_commit_claims_without_tests` is a gate, and empty is
    a pass. So the plan is made outside their `try` and a failure to make it reaches the caller.

    The positive half is the same repository with its sources and a history that cannot be read,
    which still answers empty, as it always did.

    Delete this and a checkout where nothing was generated switches the closed-with-no-test gate
    off without a word."""
    nothing = tmp_path_factory.mktemp("nothing")
    monkeypatch.setattr(sweeps, "REPO", nothing)
    for helper in (
        sweeps._commit_claims_without_tests,
        sweeps._claims_that_name_no_leaf,
        sweeps._source_claims_never_closed_by_a_commit,
    ):
        with pytest.raises(GeneratedFilesError):
            helper()

    def no_history(*args: object, **kwargs: object) -> object:
        raise subprocess.CalledProcessError(128, "git")

    monkeypatch.setattr(sweeps, "REPO", checkout)
    monkeypatch.setattr(status, "closed_task_ids", no_history)
    assert sweeps._commit_claims_without_tests() == ()
    assert sweeps._source_claims_never_closed_by_a_commit() == 0


def test_a_failed_generation_is_one_line_on_stderr_and_a_failing_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command a developer is told to run, and a sweep that cannot read the plan, both end
    in a sentence and a non-zero status; and the success path says what changed.

    Delete this and the entry points print a traceback, or exit zero having made nothing."""

    def refuse(repo: Path) -> tuple[str, ...]:
        raise GeneratedFilesError("node was not found, so nothing was made")

    monkeypatch.setattr(wbs_generate, "generate", refuse)
    assert wbs_generate.main([]) == 1
    assert "node was not found" in capsys.readouterr().err

    monkeypatch.setattr(wbs_generate, "generate", lambda repo: ("wbs.json",))
    assert wbs_generate.main([]) == 0
    assert "wbs.json changed" in capsys.readouterr().out

    monkeypatch.setattr(wbs_generate, "generate", lambda repo: ())
    assert wbs_generate.main([]) == 0
    assert "unchanged" in capsys.readouterr().out

    # `ensure` remembers a success for the process, so an earlier test's would hide this refusal.
    wbs_generate.ensure.cache_clear()
    monkeypatch.setattr(wbs_generate, "generate", refuse)
    assert sweeps.main(["traceability"]) == 1
    assert "FAIL traceability: node was not found" in capsys.readouterr().err


def test_the_generated_files_are_ignored_so_a_stray_add_cannot_commit_them() -> None:
    """Parsed from `.gitignore`, one entry per line, not searched for as text a comment could
    supply. A file that is listed is one `git add .` leaves alone.

    Delete this and the first pull request that runs `git add -A` after generating puts the three
    files back, and every conflict this change removed returns."""
    lines = {
        one.strip()
        for one in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if one.strip() and not one.lstrip().startswith("#")
    }
    for name in GENERATED:
        assert f"docs/{name}" in lines


def test_node_is_taken_from_the_path_first_and_from_homebrew_when_the_path_has_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-login shell on the Mac has no `/opt/homebrew/bin` on its PATH (CLAUDE.md), and a
    node the user put on the PATH deliberately must win over a guessed location.

    Delete this and either a Mac shell that works for every other tool fails here, or a chosen
    node is silently replaced by a fixed one."""
    guessed = tmp_path / "node"
    guessed.write_text("", encoding="utf-8")
    # The first location holds nothing, so the lookup has to go on to the second.
    monkeypatch.setattr(
        wbs_generate, "FALLBACK_NODE", (str(tmp_path / "nowhere" / "node"), str(guessed))
    )

    monkeypatch.setattr(shutil, "which", lambda name: "/chosen/bin/node")
    assert wbs_generate.find_node() == "/chosen/bin/node"

    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert wbs_generate.find_node() == str(guessed)


def test_a_script_that_runs_and_writes_nothing_is_named_not_assumed_to_have_worked(
    checkout: Path,
) -> None:
    """The scripts are trusted to write three files. If `render.js` is changed to write somewhere
    else, generation has to say which file did not appear rather than report success over an
    old one.

    Delete this and a renamed output leaves readers on whatever file was last there."""
    render = checkout / "docs" / "wbs" / "render.js"
    text = render.read_text(encoding="utf-8")
    assert '"/../wave-windows.json"' in text
    render.write_text(
        text.replace('"/../wave-windows.json"', '"/../wave-windows.elsewhere"'), "utf-8"
    )

    with pytest.raises(GeneratedFilesError, match=r"did not write wave-windows\.json"):
        generate(checkout)
    assert not (checkout / "docs" / "wave-windows.json").exists()


def test_the_command_names_this_module_and_node_is_looked_for_where_homebrew_puts_it() -> None:
    """Both are facts about somewhere else, so neither is compared with the constant that states
    it. The command has to be this module run by name, and the fallback location has to be the
    directory CLAUDE.md says Homebrew installs to, since a constant asserted against itself stays
    green for any value.

    Delete this and a message can tell a developer to run a module that is not there, or the Mac
    fallback can point at a directory nothing installs to."""
    assert f"uv run python -m {wbs_generate.__name__}" == COMMAND
    assert Path(wbs_generate.__file__).name == "wbs_generate.py"
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "`node`" in claude
    assert "/opt/homebrew/bin" in claude
    assert "/opt/homebrew/bin/node" in wbs_generate.FALLBACK_NODE
    assert wbs_generate.TIMEOUT_SECONDS >= 30, "a bound shorter than a slow runner needs"


def _steps(job: str) -> list[dict[str, object]]:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8"))
    steps: list[dict[str, object]] = workflow["jobs"][job]["steps"]
    return steps


def _index_of(job: str, needle: str) -> int:
    for position, step in enumerate(_steps(job)):
        if needle in str(step.get("run", "")):
            return position
    raise AssertionError(f"no step in the {job} job runs {needle!r}")


def test_every_ci_job_that_reads_the_generated_files_outside_pytest_makes_them_first() -> None:
    """Pytest makes them itself; these three do not run through it. The tracker job asks the
    generator whether the sources are accepted before it runs the register's check, the console
    job before its audit test reads the leaf ids, and the stack job before the image is built
    that is then asked for `/build/tracker`.

    Parsed from the workflow's YAML, not searched for in its text, so a comment cannot supply it.
    Delete this and moving a step above its generator leaves a job that fails on a clean
    checkout, or worse a Dockerfile that bakes in an image with no tracker.

    The old diff of the committed copy is asserted gone too, since the files are not committed."""
    command = "src/brain/ops/wbs_generate.py"
    assert _index_of("docs", command) < _index_of("docs", "python -m brain.requirements")
    assert _index_of("console", command) < _index_of("console", "npm run test")
    assert _index_of("stack", command) < _index_of("stack", "docker build")
    for job in ("docs", "console", "stack"):
        assert not any("git diff --exit-code" in str(one.get("run", "")) for one in _steps(job))


def _run_pytest_in(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", str(project / "tests")],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=300,
    )


def test_a_pytest_session_generates_the_files_before_a_test_reads_them(tmp_path: Path) -> None:
    """The real `tests/conftest.py` in a project of its own: sources present, no output, and one
    test that asserts the output exists. Run in a subprocess because the hook under test is
    `pytest_sessionstart`, which has already run for this session.

    Delete this and the hook can be removed with the suite green wherever the files happen to be
    lying about from an earlier run, and red only on a clean CI checkout."""
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    shutil.copyfile(ROOT / "tests" / "conftest.py", project / "tests" / "conftest.py")
    shutil.copytree(ROOT / "docs" / "wbs", project / "docs" / "wbs")
    (project / "tests" / "test_probe.py").write_text(
        "from pathlib import Path\n\n\n"
        "def test_the_plan_is_there() -> None:\n"
        "    root = Path(__file__).resolve().parents[1]\n"
        "    for name in ('wbs.json', 'tracker.html', 'wave-windows.json'):\n"
        "        assert (root / 'docs' / name).stat().st_size > 100\n",
        encoding="utf-8",
    )

    done = _run_pytest_in(project)

    assert done.returncode == 0, done.stdout + done.stderr
    assert "1 passed" in done.stdout


def test_a_pytest_session_that_cannot_generate_stops_with_the_sentence_and_runs_nothing(
    tmp_path: Path,
) -> None:
    """The same project with no sources: the session ends with pytest's usage-error status and
    the one sentence, and the probe test is never collected as a pass.

    Delete this and a failed generation lets the suite run, with a hundred tests each reporting
    a missing file in its own words."""
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    shutil.copyfile(ROOT / "tests" / "conftest.py", project / "tests" / "conftest.py")
    (project / "tests" / "test_probe.py").write_text(
        "def test_it_ran() -> None:\n    assert True\n", encoding="utf-8"
    )

    done = _run_pytest_in(project)

    assert done.returncode == 4, done.stdout + done.stderr
    assert "nothing to generate" in done.stdout + done.stderr
    assert "passed" not in done.stdout
