"""The files the work breakdown generates, and the one place that makes them.

`docs/wbs.json`, `docs/tracker.html` and `docs/wave-windows.json` are produced from
`docs/wbs/*.js` by `node docs/wbs/export.js` and `node docs/wbs/render.js`. **They used to be
committed, and that was the single largest cause of pull requests going DIRTY** (measured
2026-10-19: 76 of the last 612 commits to main touched them, and a pull request that conflicts
gets no CI). Every pull request that changed a task regenerated the same three files, so the
first one to merge conflicted every other one that had regenerated them, in files nobody had
edited by hand. They are not committed now. A pull request changes sources only, and anything
that needs the output makes it from the sources it has.

**Generated on the machine that reads them, every time, not checked against a copy.** The cheap
design was a bot committing the output to main after each merge. That keeps a stale file in the
tree between merges, so a pull request adding a leaf would run its tests against the leaf list
from before it; it puts a second commit on main per merge, and every push to main deploys; and it
needs a credential that can write to the protected branch. Generating on use costs 0.2 seconds
(measured: 0.19 seconds for both scripts) and cannot be stale, because there is no copy to go
stale. The image build already did it (`deploy.yml`), so the page the server shows was never the
committed copy.

**Generated in a scratch directory and moved into place, never in place.** Both scripts write
next to themselves (`__dirname/..`). Run in the working tree, a second pytest process reading
`wbs.json` while the first rewrites it sees a file cut to nothing. So the sources are copied to a
temporary directory, the scripts run there, and each output replaces its file with a single
rename, and only when its bytes differ. A reader sees the old file or the new one, never half.

**A failure is one sentence that names the command.** Node missing, a source the scripts refuse
(an id in `progress.js` that names no leaf, an act whose sentence no longer matches), or a reader
asked for a file nobody generated: each raises `GeneratedFilesError` with a message saying what
to run, because a missing file that reads as an empty plan is the failure this module exists to
refuse. `brain.status.load_wbs` raises `GeneratedFileMissing` for an absent file, and
`brain.ops.sweeps` lets it through where it used to swallow every error from reading the plan,
which would have switched off the "closed with no test" gate on a checkout where nobody had
generated anything.

What was rejected. Keeping the files committed and diffing in CI (the old `Tracker matches the
WBS` job), which is the thing that conflicted. A bot commit to main, above. And generating inside
the image build only: the tests read these files long before an image exists.

Not covered here, on purpose: `docs/console-audit/` (rendered by a vitest from the console's
toolchain and the live API schema, and already split one file per area so two changes meet only
when they touch the same area), `docs/delivery-checklist.md` (changes only when `acts.js` does,
once in the last 600 commits), and the installer's scripts and `docker-compose.full.yml` (a
client install needs them in the repository).

Standard library only, because the `changes` job and the pre-push hook run it before an
environment exists.

Task ids: none
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import Final

#: Why nothing is committed. Named so a reviewer meeting a regenerated file in a diff has the rule.
GENERATED_FILES_ARE_NEVER_COMMITTED: Final = (
    "docs/wbs.json, docs/tracker.html and docs/wave-windows.json are generated from "
    "docs/wbs/*.js and are not committed, because every pull request that regenerated them "
    "conflicted with every other one; run `uv run python -m brain.ops.wbs_generate` to make them"
)

#: The files the scripts write into `docs/`, in the order they are written.
GENERATED: Final[tuple[str, ...]] = ("wbs.json", "tracker.html", "wave-windows.json")

#: The scripts, in order. `render.js` reads the same sources and writes the other two files.
SCRIPTS: Final[tuple[str, ...]] = ("export.js", "render.js")

#: The command a developer runs, quoted in every message.
COMMAND: Final = "uv run python -m brain.ops.wbs_generate"

#: Where Homebrew puts node, which a non-login shell may not have on its PATH (CLAUDE.md).
FALLBACK_NODE: Final[tuple[str, ...]] = ("/opt/homebrew/bin/node", "/usr/local/bin/node")

#: The longest either script may take. Measured at 0.1 seconds; the bound is for a hung node.
TIMEOUT_SECONDS: Final = 120


class GeneratedFilesError(RuntimeError):
    """The generated files could not be made, said in one sentence that names what to run."""


class GeneratedFileMissing(GeneratedFilesError, FileNotFoundError):  # noqa: N818  names a state
    """A reader was handed a generated file nobody had generated.

    Also a `FileNotFoundError`, so a caller that already handles an absent file still does.
    """


def missing_message(path: Path) -> str:
    """The one sentence for a generated file that is not there."""
    return (
        f"{path.name} is generated from docs/wbs/*.js and is not committed, so run "
        f"`{COMMAND}` (or `node docs/wbs/export.js && node docs/wbs/render.js`) first"
    )


def require(path: Path) -> Path:
    """`path`, or `GeneratedFileMissing` when it is one of the generated files and is absent."""
    if path.name in GENERATED and not path.exists():
        raise GeneratedFileMissing(missing_message(path))
    return path


def find_node() -> str:
    """The node executable, or a sentence saying how to get one."""
    found = shutil.which("node")
    if found is not None:
        return found
    for candidate in FALLBACK_NODE:
        if Path(candidate).is_file():
            return candidate
    msg = (
        "node was not found, and docs/wbs.json is generated by it: install Node 22 (on a Mac "
        "`brew install node`) and run `" + COMMAND + "`"
    )
    raise GeneratedFilesError(msg)


def _refusal(script: str, stderr: str) -> str:
    """The line of a node failure that says why, not the stack under it."""
    lines = [one.strip() for one in stderr.splitlines() if one.strip()]
    why = next((one for one in lines if "Error" in one and not one.startswith("at ")), "")
    detail = " ".join(lines[lines.index(why) :][:4]) if why else " ".join(lines[-2:])
    return f"docs/wbs/{script} refused the work breakdown: {detail[:400]}"


def generate(repo: Path) -> tuple[str, ...]:
    """Make the generated files under `repo/docs`, and return the names whose bytes changed.

    Raises `GeneratedFilesError` and leaves every existing output untouched when either script
    fails, so a broken source never replaces a good file with half of one.
    """
    sources = repo / "docs" / "wbs"
    scripts = sorted(sources.glob("*.js"))
    if not all((sources / one).is_file() for one in SCRIPTS):
        msg = f"export.js and render.js are not in {sources}, so there is nothing to generate"
        raise GeneratedFilesError(msg)
    node = find_node()
    with tempfile.TemporaryDirectory(prefix="wbs-generate-") as scratch:
        work = Path(scratch) / "docs" / "wbs"
        work.mkdir(parents=True)
        for one in scripts:
            shutil.copyfile(one, work / one.name)
        for script in SCRIPTS:
            try:
                done = subprocess.run(  # noqa: S603  node and two literal script names, no shell
                    [node, str(work / script)],
                    cwd=scratch,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as error:
                msg = f"docs/wbs/{script} did not finish in {TIMEOUT_SECONDS} seconds"
                raise GeneratedFilesError(msg) from error
            if done.returncode != 0:
                raise GeneratedFilesError(_refusal(script, done.stderr))
        made = {name: work.parent / name for name in GENERATED}
        absent = [name for name, one in made.items() if not one.is_file()]
        if absent:
            msg = f"docs/wbs/export.js and render.js ran and did not write {', '.join(absent)}"
            raise GeneratedFilesError(msg)
        return _move_into_place(repo / "docs", made)


def _move_into_place(docs: Path, made: dict[str, Path]) -> tuple[str, ...]:
    changed: list[str] = []
    docs.mkdir(parents=True, exist_ok=True)
    for name, produced in made.items():
        wanted = produced.read_bytes()
        target = docs / name
        if target.is_file() and target.read_bytes() == wanted:
            continue
        # A temporary file beside the target and one rename, so a concurrent reader sees the old
        # file or the new one. `delete=False` because the rename is what removes the name.
        with tempfile.NamedTemporaryFile(dir=docs, prefix=f".{name}.", delete=False) as handle:
            handle.write(wanted)
            staged = Path(handle.name)
        staged.replace(target)
        changed.append(name)
    return tuple(changed)


@cache
def ensure(repo: Path) -> tuple[str, ...]:
    """`generate`, once per process per repository, for the readers that may call it repeatedly."""
    return generate(repo)


def main(argv: Sequence[str] | None = None) -> int:
    """Generate for this repository. `uv run python -m brain.ops.wbs_generate`."""
    del argv
    repo = Path(__file__).resolve().parents[3]
    try:
        changed = generate(repo)
    except GeneratedFilesError as error:
        print(error, file=sys.stderr)
        return 1
    print(
        f"generated {', '.join(GENERATED)}"
        + (f" ({', '.join(changed)} changed)" if changed else " (unchanged)")
    )
    return 0


if __name__ == "__main__":  # pragma: no cover  the module entry point, exercised by main()
    raise SystemExit(main())
