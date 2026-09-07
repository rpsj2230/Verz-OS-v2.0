"""The repository is the template, and Verz is one deployment of it.

Four claims that are about this checkout rather than about the running system: the
environment file is the declaration's printout, the product is named by the installation
rather than by a literal, the map of what an install touches agrees with the tree, and
nothing here contains or fetches a second copy of this repository.

They live apart from `test_independence.py` because that file is about the sweep, which is a
rule applied to source, and these are about documents. The practical reason is smaller and
worth recording: a single `Task ids:` line naming all twelve leaves is 105 characters, and the
line may not wrap, so the split was going to happen somewhere.

Task ids: M41.3.1 M41.3.2 M41.3.3 M41.3.4
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_the_environment_example_is_the_declarations_printout() -> None:
    """**A hand-kept list of environment variables is wrong the first time somebody adds one,
    and it is wrong by omitting the new one**, which is the direction nobody notices: the
    install team sets the fourteen that are written down and the fifteenth quietly takes its
    default on a client's server.

    So `.env.example` carries a generated block and this compares it against the declaration.
    Editing a value in the file is expected, because it is an example; editing a name or a
    meaning, or adding a setting and forgetting the file, fails here.

    Delete this and a client install is a release tag plus an environment file that does not
    mention everything the release reads."""
    from brain.install import ENV_BLOCK_END, ENV_BLOCK_START, env_example

    text = (REPO / ".env.example").read_text(encoding="utf-8")

    assert ENV_BLOCK_START in text and ENV_BLOCK_END in text
    start = text.index(ENV_BLOCK_START)
    end = text.index(ENV_BLOCK_END) + len(ENV_BLOCK_END)
    assert text[start:end].strip() == env_example().strip()


def test_the_product_is_named_by_the_installation_and_not_by_a_literal() -> None:
    """**The first thing an API consumer sees and the first thing on every build page.** The
    FastAPI schema title and the two page titles all read "Verz Company Brain" until today,
    which is a product wearing one deployment's name in the three most visible places it has.

    A shape-based sweep cannot catch this: a company name has no shape, unlike an address or a
    host. So it is asserted from the other end, by configuring a different company and
    checking the rendered output changes, which is a property no literal can satisfy.

    Delete this and the name goes back to a constant, and the second client's staff read
    somebody else's company name on every page."""
    from fastapi.testclient import TestClient

    from brain.app import create_app
    from brain.install import installed_name

    assert installed_name({"INSTALL_COMPANY_NAME": "Acme"}) == "Acme Brain"
    assert (
        installed_name({"INSTALL_PRODUCT_NAME": "Knowledge Desk"}) == "Your Company Knowledge Desk"
    )

    client = TestClient(create_app())
    assert installed_name() in client.get("/build").text


def test_the_repository_map_names_every_top_level_entry_and_invents_none() -> None:
    """`docs/repository-map.md` is what tells a reader which parts of this tree an install
    touches, and the answer is none of them. A map that has drifted is worse than none: it
    describes a repository that no longer exists, and the entry it is missing is the new one,
    which is exactly the one somebody is looking up.

    Both directions, because a map naming a directory that was deleted misleads as reliably as
    one missing a directory that was added.

    Delete this and the map rots the first time anybody adds a compose file."""
    raw = (REPO / "docs" / "repository-map.md").read_text(encoding="utf-8")
    # Whitespace collapsed before any phrase is looked for. The document is wrapped at ninety
    # columns, so "a release tag plus one environment file" is split across two lines and a
    # plain substring check fails on a document that says exactly what it should. That is the
    # substring trap CLAUDE.md records, in the direction that produces a false alarm.
    text = " ".join(raw.split())

    # Dot-entries are tooling and caches rather than repository structure, and a map that
    # listed `.mypy_cache` would be describing this laptop rather than the product. `.env.example`
    # is the exception and is asserted separately below, because it is the one file an install
    # copies.
    def family(name: str) -> str:
        """The compose files are one family in the map, matching how they are read."""
        return "docker-compose" if name.startswith("docker-compose") else name

    # Matched against the table's own rows rather than against the document, and a mutation
    # found the difference: deleting the `migrations/` row left the word elsewhere in the
    # prose, so a bare substring check passed on a map that had lost an entry. That is the
    # substring trap CLAUDE.md records, in the direction that produces a false pass.
    named: set[str] = set()
    for line in raw.splitlines():
        if not line.startswith("|"):
            continue
        # Every backticked token in the first cell, because a row legitimately covers several
        # files: `pyproject.toml`, `uv.lock` is one row and two entries.
        for token in re.findall(r"`([^`]+)`", line.split("|")[1]):
            named.add(family(token.strip().rstrip("/").replace("*.yml", "")))
    # Read from git rather than from `iterdir`, because the claim is about the repository and
    # `iterdir` answers about this laptop. A scratch file somebody has not committed is not
    # repository structure, and a map that had to describe one would be describing a moment.
    # Found the hard way: a second agent working in this tree left a file at the root and
    # this test went red for a shape it is not about.
    tracked = subprocess.run(
        ["git", "ls-files", "--full-name", "--"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout.splitlines()
    assert len(tracked) > 100, "git listed almost nothing, so an empty difference proves nothing"

    present = {
        family(one.split("/")[0]) for one in tracked if not one.split("/")[0].startswith(".")
    }
    missing = sorted(present - named)
    assert missing == [], f"the map does not mention {missing}"
    assert ".env.example" in text
    assert "a release tag plus one environment file" in text


# --- no second copy of this repository (M41.3.2) ----------------------------------------------


def a_repository(
    root: Path, *, dockerfile: str = "FROM python:3.13-slim\nCOPY src ./src\n"
) -> Path:
    """A tree with the shape `duplication_gaps` reads, and nothing wrong with it.

    Built rather than pointed at a fixture directory, because every finding this checks for is
    a thing that must not be committed to this repository: a nested `.git` inside `tests/`
    would be a second checkout, which is the exact condition under test."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir()
    (root / "Dockerfile").write_text(dockerfile, encoding="utf-8", newline="\n")
    return root


def test_nothing_in_this_repository_fetches_or_contains_a_second_copy_of_it() -> None:
    """The claim M41.3.2 makes, held against the tree rather than asserted in a paragraph.

    **Guarded by what was read, because an empty finding and an empty scan look identical.**
    A glob that matched nothing, a build-input list that lost the Dockerfile, or a pattern
    that compiled to something unmatchable all return the same clean tuple as a clean
    repository. So the inputs are counted and the two that carry the most are named.

    Delete this and the check can be reduced to `return ()` with nothing to notice, which is
    what happened to three sweeps in this repository before they were tested this way."""
    from brain.ops.independence import build_inputs, duplication_gaps

    inputs = build_inputs(REPO)
    names = {one.name for one in inputs}

    assert len(inputs) > 20, f"only {len(inputs)} build inputs were read"
    assert "Dockerfile" in names
    assert "pyproject.toml" in names
    assert len([one for one in names if one.startswith("docker-compose")]) >= 8

    assert duplication_gaps(REPO) == ()


def test_a_checkout_vendored_inside_the_tree_is_found(tmp_path: Path) -> None:
    """A second `.git` below the root is somebody's clone of another repository sitting inside
    this one, and it is invisible in every ordinary view: `git status` ignores it, the file
    listing shows an ordinary directory, and the tests inside it never run.

    The repository's own `.git` is skipped, and asserted to be skipped, because every path
    under it contains the name and a check that reported the object store would report the
    clean case as a finding on every run.

    Delete this and the only shape of second copy that is visible from inside the tree stops
    being looked for."""
    from brain.ops.independence import duplication_gaps

    root = a_repository(tmp_path / "repo")

    assert duplication_gaps(root) == ()

    (root / "vendor" / "other").mkdir(parents=True)
    (root / "vendor" / "other" / ".git").mkdir()
    found = duplication_gaps(root)

    assert len(found) == 1
    assert "vendor/other" in found[0]
    assert "vendored" in found[0]


def test_a_submodule_is_found(tmp_path: Path) -> None:
    """A submodule is the respectable version of the same thing: a second repository whose
    version this one pins, so a fix there is two releases rather than one, and the pin is
    updated by hand or not at all.

    Delete this and a submodule can be added, and the map in `docs/repository-map.md` keeps
    saying an install is a release tag plus one environment file."""
    from brain.ops.independence import duplication_gaps

    root = a_repository(tmp_path / "repo")
    (root / ".gitmodules").write_text('[submodule "x"]\n', encoding="utf-8", newline="\n")

    found = duplication_gaps(root)

    assert len(found) == 1
    assert ".gitmodules" in found[0]


def test_a_build_that_clones_is_found_and_a_comment_about_cloning_is_not(tmp_path: Path) -> None:
    """The shape a reader of the directory listing would miss entirely: a second repository
    that never appears in the source tree and is in the image anyway. `git clone` in a
    Dockerfile, a `git+https://` requirement, a workflow calling `gh repo clone`.

    The negative half matters as much. `A_COMMENT_CANNOT_BE_DEPLOYED` is this module's own
    argument for the other direction, and it applies unchanged here: a commented-out clone
    fetches nothing, and a comment recording that the build deliberately does not clone would
    otherwise be reported for containing the words it is about. That is not hypothetical, it
    is the sentence somebody writes immediately after reading this finding.

    Delete this and either the check stops seeing the only shape that reaches production
    without touching the tree, or it starts reporting the comment that explains itself."""
    from brain.ops.independence import duplication_gaps

    cloning = a_repository(
        tmp_path / "clones",
        dockerfile="FROM python:3.13-slim\nRUN git clone https://example.invalid/other.git\n",
    )
    found = duplication_gaps(cloning)

    assert len(found) == 1
    assert "Dockerfile:2" in found[0]

    commented = a_repository(
        tmp_path / "comments",
        dockerfile=(
            "FROM python:3.13-slim\n"
            "# built from this repository only; nothing here runs git clone\n"
            "COPY src ./src\n"
        ),
    )

    assert duplication_gaps(commented) == ()


def test_the_reason_is_written_where_the_next_person_to_want_a_fork_will_read_it() -> None:
    """The check refuses three shapes; the reason it refuses them is a sentence about what
    happens six months later, and nobody derives that from a finding.

    Anchored to the document as well as to the constant, because `docs/repository-map.md` is
    where somebody proposing a per-client branch would look first and it claims this leaf.

    Delete this and the rule survives as a machine refusing an edit for reasons it does not
    give."""
    from brain.ops.independence import (
        A_SECOND_COPY_IS_SILENT_UNTIL_A_CLIENT_MEETS_THE_BUG_THAT_WAS_FIXED as WHY,
    )

    assert "twice" in WHY
    assert "release tag plus one environment file" in WHY

    text = " ".join((REPO / "docs" / "repository-map.md").read_text(encoding="utf-8").split())

    assert "no per-client branch, no per-client fork and no per-client directory" in text
    assert "M41.3.2" in text


def test_every_shape_of_fetching_a_repository_is_recognised_in_the_file_it_appears_in(
    tmp_path: Path,
) -> None:
    """**A mutation asked for this.** Dropping `git+https://` from the pattern left every
    other test green, because all of them planted a `git clone` in a Dockerfile: one shape,
    tested four ways. A dependency fetched from a repository is the shape most likely to be
    added by somebody who is not thinking about forks at all, because it looks like a
    dependency rather than like a second copy of anything, and it is pinned by a branch name
    that moves.

    Each shape is planted in the file it would really appear in, so this also holds
    `BUILD_INPUTS` to covering those files: a workflow directory dropped from the globs
    fails here rather than silently narrowing what is watched.

    Delete this and three of the four shapes can leave the pattern with nothing to say
    so."""
    from brain.ops.independence import duplication_gaps

    shapes = {
        "Dockerfile": "RUN git clone https://example.invalid/other.git\n",
        "pyproject.toml": 'dependencies = ["thing @ git+https://example.invalid/thing"]\n',
        ".github/workflows/ci.yml": "    - run: gh repo clone example/other\n",
        "ops/setup.sh": "git submodule update --init\n",
    }

    for name, line in shapes.items():
        root = a_repository(tmp_path / name.replace("/", "_").replace(".", "_"))
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(line, encoding="utf-8", newline="\n")

        found = duplication_gaps(root)

        assert len(found) == 1, f"{name}: {found}"
        assert name in found[0], f"{name} was not the file reported: {found[0]}"
