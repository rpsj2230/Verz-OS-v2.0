"""Which merges leave the worker running: the fingerprint of what a worker runs.

Against real git repositories, because the fingerprint is made from the committed tree and a fake
tree would prove only that the fake is read. The script that compares two fingerprints on the
server is tested in `tests/unit/test_brain_deploy.py`, including one test that makes the manifests
from a real repository and runs the script on them.

Task ids: M38.1.3.5, M38.5.1
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from brain.ops.release_manifest import ReleaseManifest, build_manifest
from brain.ops.restart_scope import (
    FINGERPRINT_PATTERN,
    INERT_PREFIXES,
    WORKER_FINGERPRINT_KEY,
    fingerprint,
    fingerprint_of,
    is_inert,
    tree_entries,
)

REPO = Path(__file__).resolve().parents[2]

#: Paths a merge can change without changing anything a worker runs.
INERT_PATHS = (
    "docs/needs-rupash.md",
    "docs/wbs/progress.js",
    "docs/requirements/register.json",
    "tests/unit/test_thing.py",
    "console/src/pages/Home.tsx",
    "console/package-lock.json",
    "e2e/specs/login.spec.ts",
    "matcher/Dockerfile",
    ".github/workflows/ci.yml",
)

#: Paths whose change a worker could notice, and so must restart it. Several are here because a
#: list of what is inert has to fail toward restarting, and each is a path somebody would
#: plausibly call harmless: the deploy scripts, a compose file, a lock file, and a directory this
#: repository does not have yet.
WORKER_PATHS = (
    "src/brain/ops/worker.py",
    "migrations/versions/0001_first.py",
    "alembic.ini",
    "pyproject.toml",
    "uv.lock",
    "Dockerfile",
    ".dockerignore",
    "docker-compose.worker.yml",
    "ops/deploy/brain-deploy",
    "ops/keycloak/realm-export.json",
    "README.md",
    "a_directory_nobody_has_made_yet/anything.txt",
    "docs-extra/page.md",
    "consoles/page.md",
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def _write(repo: Path, name: str, text: str) -> None:
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def _commit(repo: Path, message: str = "change") -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository holding one file at every path either list above names, and one commit."""
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "Test")
    for name in (*INERT_PATHS, *WORKER_PATHS):
        _write(work, name, f"{name} at the start\n")
    _commit(work, "start")
    return work


# ---------------------------------------------------------------------------- the rule
@pytest.mark.parametrize("path", INERT_PATHS)
def test_a_merge_that_changes_only_an_inert_path_leaves_the_fingerprint_where_it_was(
    repo: Path, path: str
) -> None:
    """A change to a build document, a test, the console's source, an end-to-end spec, the matcher
    or a workflow is not something a worker runs, so the fingerprint, and with it the decision to
    leave the worker running, is the same before and after.

    Delete this and the inert list can shrink until every merge restarts the worker again, which is
    how the owner's acceptance runs were killed all night."""
    before = fingerprint_of(repo)
    _write(repo, path, f"{path} changed\n")
    _commit(repo)

    assert FINGERPRINT_PATTERN.match(before)
    assert fingerprint_of(repo) == before


@pytest.mark.parametrize("path", WORKER_PATHS)
def test_a_merge_that_changes_a_path_a_worker_could_run_moves_the_fingerprint(
    repo: Path, path: str
) -> None:
    """The sibling of the test above, and the one that matters more: a rule tested only by the
    changes it ignores is satisfied by a fingerprint that never moves. Each path here is one a
    worker, or the image it runs from, could notice, including a directory that does not exist yet
    and two whose names merely begin like an inert one.

    Delete this and the inert list can grow to cover source, and a worker is left on old code with
    every check green (`A_PATH_NOT_NAMED_INERT_RESTARTS_THE_WORKER`)."""
    before = fingerprint_of(repo)
    _write(repo, path, f"{path} changed\n")
    _commit(repo)

    assert fingerprint_of(repo) != before


def test_a_new_file_and_a_removed_file_and_a_renamed_one_each_move_the_fingerprint(
    repo: Path,
) -> None:
    """The fingerprint covers which files there are as well as what is in them, so adding a module,
    deleting one and moving one without touching its bytes all count.

    Delete this and a rename or a deletion can leave a worker running code that no longer exists in
    the release."""
    start = fingerprint_of(repo)
    _write(repo, "src/brain/added.py", "X = 1\n")
    _commit(repo)
    added = fingerprint_of(repo)
    _git(repo, "mv", "src/brain/added.py", "src/brain/moved.py")
    _commit(repo)
    moved = fingerprint_of(repo)
    _git(repo, "rm", "-q", "src/brain/moved.py")
    _commit(repo)

    assert len({start, added, moved}) == 3
    assert fingerprint_of(repo) == start


def test_the_fingerprint_is_of_the_committed_tree_and_not_the_working_directory(
    repo: Path,
) -> None:
    """CI regenerates the status and the tracker in the checkout before the manifest is written, and
    a developer may have a half-edited module. Neither is in the release, so neither is in the
    fingerprint.

    Delete this and a file edited or generated after the commit moves the fingerprint of a release
    that does not contain it, which restarts the worker for nothing, or a stray edit hides a real
    change by being in both."""
    committed = fingerprint_of(repo)
    _write(repo, "src/brain/ops/worker.py", "edited and not committed\n")
    _write(repo, "src/brain/untracked.py", "new and not added\n")

    assert fingerprint_of(repo) == committed


def test_the_fingerprint_is_of_the_ref_asked_for(repo: Path) -> None:
    """The manifest is made for the commit being built, which is not always the one checked out.

    Delete this and the fingerprint can be of whatever is at `HEAD` while the manifest names
    another commit."""
    first = _git(repo, "rev-parse", "HEAD")
    _write(repo, "src/brain/ops/worker.py", "second\n")
    _commit(repo)

    assert fingerprint_of(repo, first) != fingerprint_of(repo, "HEAD")
    assert fingerprint_of(repo, first) == fingerprint_of(repo, first[:12])


def test_paths_with_spaces_and_non_ascii_names_are_read_whole(repo: Path) -> None:
    """The tree is listed with NUL separators, so a name with a space, a quote or a character
    outside ASCII is one path and not a quoted fragment.

    Delete this and the listing can be changed to a line-based form that splits such a name, and a
    change to the file is then counted under a path that does not exist."""
    before = fingerprint_of(repo)
    _write(repo, 'src/brain/a file "quoted" é.py', "X = 1\n")
    _commit(repo)

    assert ('src/brain/a file "quoted" é.py') in {path for path, _ in tree_entries(repo)}
    assert fingerprint_of(repo) != before


def test_the_whole_tree_is_listed_whichever_directory_git_is_asked_from(repo: Path) -> None:
    """The listing is of the commit's whole tree, so asking from inside a subdirectory still sees
    every file, the inert ones aside, and gives the fingerprint the root gives.

    Delete this and a manifest made from a subdirectory of the checkout fingerprints only that
    directory, so a change anywhere else leaves the worker running."""
    paths = {path for path, _ in tree_entries(repo / "src")}

    assert "pyproject.toml" in paths
    assert fingerprint_of(repo / "src") == fingerprint_of(repo)


# ------------------------------------------------------------------ what it will not say
def test_where_git_cannot_say_there_is_no_fingerprint_and_not_an_empty_one(tmp_path: Path) -> None:
    """A directory that is no repository, a repository with no commit and a ref that does not exist
    each give the empty string. Empty is the absence of a fingerprint, which the deploy script
    reads as restart the worker, and it is never equal to another empty one there.

    Delete this and a build made outside a repository can carry a fingerprint of nothing, which two
    such builds then share, so a worker is left running across releases that were never compared
    (`WHEN_THE_CHANGE_CANNOT_BE_TOLD_THE_WORKER_IS_RESTARTED`)."""
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    empty = tmp_path / "empty"
    empty.mkdir()
    _git(empty, "init", "-q", "-b", "main")

    assert fingerprint_of(nowhere) == ""
    assert fingerprint_of(empty) == ""
    assert fingerprint_of(empty, "no-such-ref") == ""


def test_a_tree_of_nothing_but_inert_files_has_no_fingerprint(tmp_path: Path) -> None:
    """If every committed file is inert there is nothing a worker runs to fingerprint, and a hash of
    nothing is not evidence that two releases match.

    Delete this and a repository holding only documents hashes to the same value as any other
    repository holding only documents."""
    only = tmp_path / "only"
    only.mkdir()
    _git(only, "init", "-q", "-b", "main")
    _git(only, "config", "user.email", "t@example.com")
    _git(only, "config", "user.name", "Test")
    _write(only, "docs/a.md", "a\n")
    _commit(only)

    assert fingerprint_of(only) == ""
    assert fingerprint([]) == ""
    assert fingerprint([("docs/a.md", "abc")]) == ""


def test_an_entry_with_no_blob_is_not_counted() -> None:
    """A pair with no object id is a listing that was cut short, and it is left out rather than
    hashed as an empty one.

    Delete this and a truncated listing hashes to a value that a complete listing never has, so
    the worker is restarted for nothing, or, if both listings were cut the same way, not at all."""
    full = fingerprint([("src/a.py", "abc"), ("src/b.py", "def")])

    assert fingerprint([("src/a.py", "abc"), ("src/b.py", "def"), ("src/c.py", "")]) == full


def test_the_fingerprint_does_not_depend_on_the_order_the_tree_is_listed_in() -> None:
    """Delete this and two listings of one tree in different orders can hash differently, which
    restarts a worker for a release that changed nothing."""
    entries = [("src/b.py", "2"), ("src/a.py", "1"), ("pyproject.toml", "3")]

    assert fingerprint(entries) == fingerprint(list(reversed(entries)))


def test_the_fingerprint_is_the_documented_digest_of_the_sorted_pairs() -> None:
    """The format is written down in the module and read by nothing but the comparison for
    equality, so what is pinned here is that it is a SHA-256 over the schema line and each
    `path NUL blob LF`, in path order, and that a file's blob and its path both count.

    Delete this and the schema line or the separators can change, which is harmless alone and
    which silently stops two releases built by different versions of this module matching, and a
    path or a blob can fall out of the hash without a test noticing."""
    expected = hashlib.sha256(
        b"brain.worker-fingerprint.v1\n" + b"pyproject.toml\x00bbb\n" + b"src/a.py\x00aaa\n"
    ).hexdigest()

    assert fingerprint([("src/a.py", "aaa"), ("pyproject.toml", "bbb")]) == expected
    assert fingerprint([("src/a.py", "aaa"), ("pyproject.toml", "ccc")]) != expected
    assert fingerprint([("src/z.py", "aaa"), ("pyproject.toml", "bbb")]) != expected


# ------------------------------------------------------------------- the list itself
def test_the_inert_list_is_exactly_what_the_owner_approved_and_nothing_wider() -> None:
    """Held to a literal, because widening it is the one edit that can leave a worker on old code.
    Documents, tests, the console's source and workflows are the owner's (2026-10-14); the end to
    end specs and the matcher are tests and a separate image, and nothing else is in it.

    Delete this and the list can grow without anybody being asked."""
    assert INERT_PREFIXES == (
        "docs/",
        "tests/",
        "e2e/",
        "console/",
        "matcher/",
        ".github/",
    )


@pytest.mark.parametrize("path", [*INERT_PATHS])
def test_an_inert_path_is_inert(path: str) -> None:
    """Delete this and `is_inert` can return False for everything, which is a rule that restarts
    the worker on every merge and passes every other test in this file."""
    assert is_inert(path)


@pytest.mark.parametrize("path", [*WORKER_PATHS])
def test_a_path_a_worker_could_run_is_not_inert(path: str) -> None:
    """Delete this and `is_inert` can return True for everything, which leaves the worker on old
    code for ever."""
    assert not is_inert(path)


def test_everything_the_image_copies_in_for_the_application_to_run_counts_as_the_workers() -> None:
    """Read from the Dockerfile rather than from a list in this file: every path it copies into the
    image, other than the documents and the console's bundle (which are the inert ones) and the
    release manifest itself, is something the application or a worker can run, so none of it may be
    named inert.

    Delete this and a path can be added to the image and, by being added to the inert list too,
    run in a worker that is never restarted for it."""
    lines = (REPO / "Dockerfile").read_text(encoding="utf-8").splitlines()
    sources: set[str] = set()
    for line in lines:
        if not line.startswith("COPY ") or "--from=" in line:
            continue
        parts = [word for word in line.split()[1:] if not word.startswith("--")]
        sources.update(word.rstrip("/") for word in parts[:-1])

    assert {"src", "migrations", "alembic.ini", "pyproject.toml", "uv.lock"} <= sources
    for source in sorted(sources):
        top = source.split("/")[0]
        if top in {"docs", "console"} or source.startswith("RELEASE.jso"):
            continue
        assert not is_inert(source + "/x"), source
        assert not is_inert(source), source


# --------------------------------------------------------------------- the manifest
def test_the_manifest_carries_the_fingerprint_of_the_commit_it_is_made_for(repo: Path) -> None:
    """CI's `release_manifest` run is what puts the fingerprint in the image, under the key the
    deploy script reads, and it survives being written and read back.

    Delete this and the manifest can stop carrying it, and every worker is then restarted by every
    merge again with nothing red."""
    first = _git(repo, "rev-parse", "HEAD")
    manifest = build_manifest(repo, now=datetime(2019, 1, 1, tzinfo=UTC))

    assert manifest.extra[WORKER_FINGERPRINT_KEY] == fingerprint_of(repo, first)
    again = ReleaseManifest.from_json(manifest.to_json())
    assert again.extra[WORKER_FINGERPRINT_KEY] == manifest.extra[WORKER_FINGERPRINT_KEY]
    assert re.search(rf'"{WORKER_FINGERPRINT_KEY}": "[0-9a-f]{{64}}"', manifest.to_json()), (
        "the form the deploy script's pattern reads"
    )


def test_a_manifest_made_where_git_cannot_say_carries_no_fingerprint(tmp_path: Path) -> None:
    """A repository whose every file is inert gives no fingerprint, and the manifest then leaves the
    key out, so the script reads none rather than a value.

    Delete this and the manifest can write an empty string under the key, which the script's pattern
    refuses but a reader of the file would take for an answer."""
    only = tmp_path / "only"
    only.mkdir()
    _git(only, "init", "-q", "-b", "main")
    _git(only, "config", "user.email", "t@example.com")
    _git(only, "config", "user.name", "Test")
    _write(only, "docs/a.md", "a\n")
    _commit(only)

    assert WORKER_FINGERPRINT_KEY not in build_manifest(only).extra
