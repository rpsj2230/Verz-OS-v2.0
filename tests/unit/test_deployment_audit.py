"""The audit of the areas the independence sweep does not read, and of git history.

Two halves, tested two ways. The scanner is proved against a repository this test builds, so
the property is asserted rather than inferred from whatever this checkout happens to contain.
The findings against this repository are pinned by file, because they are real and the pin is
the notification: a file dropping off the list is somebody fixing it, and a file joining it is
a client value that has just been committed.

**The findings are pinned by file and not by line.** A line number moves every time somebody
adds a comment above it, so a test pinned to the findings would fail for an edit that changed
nothing, and a test that fails for nothing gets loosened until it fails for nothing at all.

Task ids: M42.4.1
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from brain.deployment.audit import (
    HISTORY_PATHS,
    TEXT_SUFFIXES,
    UNSWEPT,
    AuditError,
    allowed_hosts_for,
    client_values_in,
    configuration_gaps,
    files_with_client_values,
    history_gaps,
    unswept_files,
)
from brain.ops.independence import SEARCHED, SEARCHED_FILES, searched_files

REPO = Path(__file__).resolve().parents[2]

#: The files in this repository that carry a client value today, as of 2026-09-09.
#:
#: **This list was ten entries and is two, and the shrinking is the record of the fix.** Eight
#: of them were `.env.example` and files under `ops/`: the environment file an install copies
#: onto a client's server, the realm every client's Keycloak is built from, the deploy scripts
#: that repeated the same host as a shell default, and the runbooks that told an administrator
#: to open it. All eight were cleaned on 2026-09-09 and both areas are now inside
#: `brain.ops.independence`, which is a hard gate, so they cannot come back quietly.
#:
#: What is left is the two workflows. They are this repository's own release pipeline rather
#: than the product, which is an argument for a different fix and not for no fix, and neither
#: is gated by anything today.
CARRYING_A_CLIENT_VALUE: tuple[str, ...] = (
    ".github/workflows/anchor.yml",
    ".github/workflows/deploy.yml",
)


def a_repository(root: Path, files: dict[str, str]) -> Path:
    """A throwaway git repository with one commit per file, in name order.

    Built rather than mocked, because `history_gaps` is a question about git and a fake that
    answered it would be a test of the fake. One commit per file so a revision walk has more
    than one thing to walk.
    """
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True, timeout=60)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
    for name in sorted(files):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[name], encoding="utf-8", newline="\n")
        subprocess.run(["git", "add", "--", name], cwd=root, check=True, timeout=60)
        subprocess.run(["git", "commit", "-q", "-m", f"add {name}"], cwd=root, check=True)
    return root


# --- what the sweep does not read ------------------------------------------------------


def test_the_areas_this_reads_are_the_ones_the_independence_sweep_does_not() -> None:
    """The premise. If any of these were already inside `brain.ops.independence.SEARCHED` this
    module would be a second implementation of a check that already runs, which is the failure
    `tests/invariants/test_single_implementation.py` exists for.

    Delete this and somebody widens `SEARCHED`, this module keeps running, and one of the two
    starts disagreeing about a host with nothing to say which. That is not hypothetical: on
    2026-09-09 `SEARCHED` grew `ops` and `SEARCHED_FILES` grew `.env.example`, this test went
    red, and shrinking `UNSWEPT` to match is what it went red for."""
    for pattern in UNSWEPT:
        area = pattern.split("/")[0]
        assert area not in SEARCHED, f"{pattern} is already swept by brain.ops.independence"
        assert pattern not in SEARCHED_FILES, f"{pattern} is already gated as a single file"


def test_the_workflows_are_what_is_left_carrying_this_deployments_own_server() -> None:
    """**The finding this module was written to make visible, and it worked.** It reported ten
    files on 2026-09-08, eight of them `.env.example` and files under `ops/`: the environment
    file every install copies, the realm imported into every client's Keycloak, the deploy
    scripts repeating the host as a shell default, and the runbooks naming it in prose. Those
    eight are fixed and both areas are inside `brain.ops.independence` now, which is a gate.

    The two that remain are workflows, and they are pinned rather than waved through: a file
    joining this list is a client value that has just been committed somewhere nothing gates.

    This test is expected to fail as each file is cleaned, and that failure is the
    notification. Delete it and the audit M42.4.1 asks for has nothing to report against."""
    found = files_with_client_values(REPO)

    assert found == CARRYING_A_CLIENT_VALUE, "the set of files carrying a client value moved"
    assert all(":" in one for one in configuration_gaps(REPO)), "a finding with no location"


def test_a_configuration_area_with_nothing_in_it_is_reported_as_clean() -> None:
    """The positive case. A scanner that reported every host would be satisfied by one that
    reports every line, and the reserved documentation domains and this deployment's own
    service names are exactly what must not be reported.

    Delete this and the audit becomes noise, which is how the real findings get skipped."""
    allowed = allowed_hosts_for(REPO)
    clean = (
        "SENDER=nobody@example.com\n"
        "HOME_PAGE=http://localhost:5173/\n"
        "BIND=0.0.0.0\n"
        "DB=postgresql://brain@db:5432/brain\n"
    )
    assert client_values_in(clean, where="clean.env", allowed=allowed) == ()


def test_a_work_address_an_address_and_a_client_host_are_each_reported() -> None:
    """Three shapes, one per line, because they are found by three different patterns and a
    test covering one would leave the other two able to return nothing.

    Delete this and the scanner could stop looking for two of the three and still pass."""
    text = (
        "SENDER=someone@acme-holdings.co\n"
        "CALLBACK=https://brain.203.0.113.9.sslip.io/auth/callback\n"
        "PEER=198.51.100.7\n"
        "# CALLBACK=https://commented.example.org/\n"
    )
    findings = client_values_in(text, where="one.env", allowed=())

    assert any("a work address" in one and "acme-holdings.co" in one for one in findings)
    assert any("a client host" in one for one in findings)
    assert any("an address" in one and "198.51.100.7" in one for one in findings)
    assert all("commented" not in one for one in findings)


def test_only_text_files_are_read_and_the_realm_is_read_by_the_gate_instead() -> None:
    """A workflow is YAML and a build input has no suffix at all, and both carry a host. A
    binary read as text produces findings that point at nothing, which is worse than missing
    it: somebody has to check each one.

    The second half is the handover. The realm and the environment file were read here until
    2026-09-09 and are read by `brain.ops.independence` now, which is a gate rather than a
    report, so reading them here as well would be two modules with one opinion each about
    whether a host belongs to a client.

    Delete this and the audit either starts reporting an image, or quietly grows a second
    answer about the realm alongside the gate's."""
    read = {one.relative_to(REPO).as_posix() for one in unswept_files(REPO)}

    assert ".github/workflows/deploy.yml" in read
    assert all(Path(one).suffix in TEXT_SUFFIXES for one in read)

    gated = {one.relative_to(REPO).as_posix() for one in searched_files(REPO)}
    for handed_over in ("ops/keycloak/realm-export.json", ".env.example"):
        assert handed_over not in read, f"{handed_over} is read here and gated as well"
        assert handed_over in gated, f"{handed_over} is read by neither this module nor the gate"


# --- git history -----------------------------------------------------------------------


def test_the_history_walk_covers_the_file_an_install_copies_and_the_realm_it_imports() -> None:
    """`HISTORY_PATHS` is a declaration, and a test that read it to check what was walked would
    be comparing it with itself. So each entry is anchored to why it is there.

    `.env.example` is the one file `docs/repository-map.md` marks as copied by an install, and
    that document is read here rather than trusted. `ops/keycloak/realm-export.json` is the
    realm imported into a client's own identity provider, so a value in its history is a value
    that was pushed to somebody else's Keycloak.

    Delete this and the list can be shortened to whichever paths happen to be clean."""
    assert ".env.example" in HISTORY_PATHS
    assert "ops/keycloak/realm-export.json" in HISTORY_PATHS

    mapped = " ".join((REPO / "docs" / "repository-map.md").read_text(encoding="utf-8").split())
    assert "`.env.example`" in mapped and "Copied" in mapped

    for path in HISTORY_PATHS:
        assert (REPO / path).is_file(), f"{path} is walked and does not exist"


def test_a_value_removed_from_the_working_tree_is_still_found_in_history(tmp_path: Path) -> None:
    """The point of reading history at all. A value deleted from a file is gone from the next
    checkout and from nowhere else: every clone, fork and CI cache still holds it, so the
    finding is a credential to rotate rather than a file to edit.

    Delete this and an audit reporting "clean" means the working tree is clean, which is the
    one thing nobody was worried about."""
    root = a_repository(tmp_path, {"one.env": "CALLBACK=https://brain.acme-holdings.co/\n"})
    (root / "one.env").write_text("CALLBACK=\n", encoding="utf-8", newline="\n")
    subprocess.run(["git", "commit", "-qam", "remove the host"], cwd=root, check=True, timeout=60)

    assert (
        client_values_in((root / "one.env").read_text(encoding="utf-8"), where="w", allowed=())
        == ()
    )
    findings = history_gaps(root, ["one.env"])
    assert len(findings) == 1
    assert "brain.acme-holdings.co" in findings[0]


def test_one_value_across_many_revisions_is_reported_once(tmp_path: Path) -> None:
    """A host that survived forty commits is one disclosure, and forty lines of it is a report
    nobody reads to the end, which means the second finding underneath it is never seen.

    Delete this and the history report is as long as the history."""
    root = a_repository(tmp_path, {"one.env": "CALLBACK=https://brain.acme-holdings.co/\n"})
    for number in range(3):
        (root / "one.env").write_text(
            f"# note {number}\nCALLBACK=https://brain.acme-holdings.co/\n",
            encoding="utf-8",
            newline="\n",
        )
        subprocess.run(["git", "commit", "-qam", f"note {number}"], cwd=root, check=True)

    assert len(history_gaps(root, ["one.env"])) == 1


def test_a_path_that_never_existed_in_a_revision_is_skipped_rather_than_raising(
    tmp_path: Path,
) -> None:
    """`HISTORY_PATHS` names files that were added at different times and one of them may not
    exist yet. An audit that raised the first time it asked about a path a revision predates
    would report nothing about any of the others.

    Delete this and adding a path to the list breaks the whole history audit."""
    root = a_repository(tmp_path, {"one.env": "A=1\n", "two.env": "B=2\n"})
    assert history_gaps(root, ["one.env", "never-existed.env"]) == ()


def test_git_failing_is_refused_rather_than_read_as_an_empty_history(tmp_path: Path) -> None:
    """An empty string from git reads as "this path has no history", which is the answer that
    makes the whole audit report nothing and pass. That is the shape `brain.ops.sweeps` keeps
    finding: a check that is green because it never looked.

    Delete this and running the audit outside a repository reports a clean history."""
    with pytest.raises(AuditError, match="git log"):
        history_gaps(tmp_path, ["one.env"])


def test_the_values_taken_out_of_these_files_are_still_in_their_history() -> None:
    """**Measured rather than hoped, and the answer changed on 2026-09-09.** Until then every
    value history held for these paths was one the working tree still held, so the exposure
    was the current files and the fix was an edit. Then the current files were fixed, and this
    is now the state the history walk was written for and had never seen: the paths are clean
    and the log is not.

    That gap is the whole point of reading history. A value removed from a file is gone from
    the next checkout and from nowhere else - every clone, fork, CI cache and backup still has
    it - so the remaining question is not "which file" but whether each value is a credential
    to rotate or a host to accept as public. See
    `A_VALUE_IN_HISTORY_IS_DISCLOSED_AND_CANNOT_BE_UNCOMMITTED`.

    Read against the files themselves rather than against `configuration_gaps`, because these
    paths are no longer in `UNSWEPT`: asking the working-tree scanner about them would compare
    history with an area it does not read and pass for the wrong reason.

    Delete this and the removal looks complete, which is the belief this module exists to
    refuse."""
    allowed = allowed_hosts_for(REPO)
    from_history = {one.split(": ", 1)[-1] for one in history_gaps(REPO, HISTORY_PATHS)}
    still_in_the_files = {
        one.split(": ", 1)[-1]
        for path in HISTORY_PATHS
        for one in client_values_in(
            (REPO / path).read_text(encoding="utf-8"), where=path, allowed=allowed
        )
    }

    assert from_history, "the history walk found nothing at all, which means it did not run"
    assert not still_in_the_files, sorted(still_in_the_files)
    assert from_history - still_in_the_files == from_history


def test_a_path_deleted_in_a_revision_is_skipped_and_a_real_git_failure_is_not(
    tmp_path: Path,
) -> None:
    """`git log` reports the commit that deleted a file, and the file is not there to read at
    that commit, so an absence is ordinary and has to be skipped. A git that could not run is
    not ordinary, and both come back as a non-zero exit with nothing on stdout: telling them
    apart is the difference between skipping one revision and reporting a clean history for a
    repository nothing was ever read from.

    `_show` is reached directly for the second half because there is no public path to it: a
    `history_gaps` call outside a repository fails at `git log` first, which is a different
    guard with its own test.

    Delete this and the audit's all-clear stops meaning anything at all."""
    from brain.deployment.audit import _show

    # The repository sits in a subdirectory so that `outside` really is outside it: git
    # walks up from the working directory, so a sibling of the repository root is still
    # inside it.
    (tmp_path / "repo").mkdir()
    root = a_repository(
        tmp_path / "repo", {"one.env": "CALLBACK=https://brain.acme-holdings.co/\n"}
    )
    (root / "one.env").unlink()
    subprocess.run(["git", "commit", "-qam", "delete it"], cwd=root, check=True, timeout=60)

    # The deleting commit is in the log and the file is not in it, which is an absence.
    findings = history_gaps(root, ["one.env"])
    assert len(findings) == 1
    assert "brain.acme-holdings.co" in findings[0]

    outside = tmp_path / "not-a-repository"
    outside.mkdir()
    with pytest.raises(AuditError, match="git show"):
        _show(outside, "HEAD", "one.env")
