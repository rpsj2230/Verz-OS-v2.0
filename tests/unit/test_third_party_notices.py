"""The third-party notices file: current with the locks, carried by the image and the archive, and
checked in CI.

**A tree is built here rather than the real one for every refusal.** The committed file is held
against the real locks by one test; every way it can be stale is shown over a small tree written
into a temporary folder, with the package index answered by a function in the test.

Task ids: M42.7.3
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.deployment.release import REPO, included_by
from brain.ops.dependency_policy import NPM_LOCKS, PYTHON_LOCKS
from brain.ops.third_party_notices import (
    NO_LICENCE,
    NOTICES_PATH,
    READ_FROM_THE_PROJECT,
    REGENERATE_WITH,
    check,
    entries_for,
    licences_for,
    main,
    parse,
    python_shipped,
    render,
    shipped,
    write,
)

UV_LOCK = """
version = 1

[[package]]
name = "brain"
version = "0.1.0"
source = { editable = "." }
dependencies = [{ name = "runtime-lib" }]

[package.dev-dependencies]
dev = [{ name = "test-runner" }]

[[package]]
name = "runtime-lib"
version = "1.2.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [{ name = "runtime-leaf" }]

[[package]]
name = "runtime-leaf"
version = "3.0.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "test-runner"
version = "9.9.9"
source = { registry = "https://pypi.org/simple" }
dependencies = [{ name = "runner-leaf" }]

[[package]]
name = "runner-leaf"
version = "1.0.0"
source = { registry = "https://pypi.org/simple" }
"""

CONSOLE_LOCK = {
    "packages": {
        "": {"dependencies": {"@fontsource/example": "1.0.0"}},
        "node_modules/@fontsource/example": {"version": "1.0.0", "license": "OFL-1.1"},
        "node_modules/bundler": {"version": "2.0.0", "license": "MIT", "dev": True},
    }
}

PIECE_LOCK: dict[str, Any] = {"packages": {"": {"dependencies": {}}}}

NEWCOMER = (
    '\n[[package]]\nname = "newcomer"\nversion = "0.1.0"\n'
    'source = { registry = "https://pypi.org/simple" }\n'
)

COMPOSE = "services:\n  db:\n    image: postgres:16\n"


def _tree(root: Path, *, uv: str = UV_LOCK, console: dict[str, Any] | None = None) -> Path:
    """The files `shipped` reads, as a small repository."""
    for name in PYTHON_LOCKS:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(uv if name == "uv.lock" else "version = 1\n", encoding="utf-8")
    for name in NPM_LOCKS:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        document = (console or CONSOLE_LOCK) if "console" in name else PIECE_LOCK
        (root / name).write_text(json.dumps(document), encoding="utf-8")
    (root / "docker-compose.yml").write_text(COMPOSE, encoding="utf-8")
    return root


def _index(url: str) -> dict[str, Any]:
    """The package index, answering a licence for every Python package asked about."""
    return {"info": {"license_expression": "MIT", "license": None, "classifiers": []}}


def _written(root: Path) -> None:
    (root / NOTICES_PATH).write_text(write(root, _index), encoding="utf-8")


def test_the_committed_notices_name_everything_the_real_locks_ship() -> None:
    """**The release fails when a dependency moved and the file did not.** Delete this and a
    bump to any lock ships a release whose notices are for last month's software, and nothing is
    red."""
    assert check(REPO) == ()


def test_the_python_set_is_what_a_no_dev_install_reaches() -> None:
    """The closure of the project's own dependencies, not the whole lock. Delete this and a test
    runner and everything it pulled in is named in a file clients read as what runs on their
    server."""
    names = {one.name for one in python_shipped(UV_LOCK, "uv.lock")}

    assert names == {"runtime-lib", "runtime-leaf"}


def test_a_build_time_console_package_is_not_listed_and_a_font_is(tmp_path: Path) -> None:
    """Fonts are packages and ship; the bundler does not. Delete this and the font licences the
    leaf names are missing, or a compiler is acknowledged as shipped."""
    found = {one.name for one in shipped(_tree(tmp_path))}

    assert "@fontsource/example" in found
    assert "bundler" not in found


def test_a_file_written_for_a_tree_passes_its_own_check(tmp_path: Path) -> None:
    """The positive case. Delete this and every refusal below is satisfied by a check that
    refuses everything."""
    root = _tree(tmp_path)
    _written(root)

    assert check(root) == ()
    held = parse((root / NOTICES_PATH).read_text(encoding="utf-8"))
    assert held[("pypi", "runtime-lib", "1.2.0")] == "MIT"
    assert held[("npm", "@fontsource/example", "1.0.0")] == "OFL-1.1"
    assert held[("image", "postgres", "")] == "PostgreSQL"


def test_a_missing_file_a_missing_component_and_a_moved_version_are_each_named(
    tmp_path: Path,
) -> None:
    """The three ways a file is stale. Delete this and a release missing a notice passes, which is
    the failure the leaf names."""
    root = _tree(tmp_path)
    assert "does not exist" in check(root)[0]
    _written(root)
    moved = UV_LOCK.replace('version = "1.2.0"', 'version = "1.3.0"')
    (root / "uv.lock").write_text(moved, encoding="utf-8")

    gaps = check(root)

    assert any(
        "pypi:runtime-lib 1.3.0 ships and the notices file does not name it" in g for g in gaps
    )
    assert any(
        "pypi:runtime-lib 1.2.0 is in the notices file and nothing ships it" in g for g in gaps
    )

    added = (
        UV_LOCK.replace(
            'dependencies = [{ name = "runtime-lib" }]',
            'dependencies = [{ name = "runtime-lib" }, { name = "newcomer" }]',
        )
        + NEWCOMER
    )
    (root / "uv.lock").write_text(added, encoding="utf-8")
    assert any("pypi:newcomer 0.1.0 ships" in g for g in check(root))


def test_a_shipped_component_with_no_licence_recorded_is_refused(tmp_path: Path) -> None:
    """A notice that says nothing is not one. Delete this and a package the index could not read
    is listed as acknowledged."""
    root = _tree(tmp_path)

    def silent(url: str) -> dict[str, Any]:
        return {"info": {"license_expression": None, "license": None, "classifiers": []}}

    (root / NOTICES_PATH).write_text(write(root, silent), encoding="utf-8")

    gaps = check(root)

    assert any(
        "pypi:runtime-lib 1.2.0 is in the notices file with no licence recorded" in g for g in gaps
    )
    assert NO_LICENCE in (root / NOTICES_PATH).read_text(encoding="utf-8")


def test_an_image_is_named_once_however_many_tags_it_runs() -> None:
    """One repository at two tags is one line. Delete this and the file lists postgres twice."""
    from brain.ops.dependency_policy import Component

    components = [
        Component("image", "postgres", "postgres:16", "a.yml"),
        Component("image", "postgres", "postgres:17", "b.yml"),
    ]
    text = render(entries_for(components, licences_for(components, _index)))

    assert text.count("- postgres: PostgreSQL") == 1


def test_only_the_two_named_packages_borrow_a_licence_the_lock_does_not_record() -> None:
    """A package whose lock records no licence is refused unless it is named. Delete this and a
    rule for any package from a scope admits the next unlicensed one."""
    from brain.ops.dependency_policy import Component

    unnamed = Component("npm", "unlicensed-thing", "1.0.0", "console/package-lock.json")
    named = Component(
        "npm", "@activepieces/shared", "1.0.0", "ops/automation/piece/package-lock.json"
    )
    found = licences_for([unnamed, named], _index)

    assert found[("npm", "unlicensed-thing")] == NO_LICENCE
    assert found[("npm", "@activepieces/shared")] == "MIT"
    assert set(READ_FROM_THE_PROJECT) == {
        ("npm", "@activepieces/pieces-framework"),
        ("npm", "@activepieces/shared"),
    }


def test_the_image_and_the_archive_carry_the_file() -> None:
    """The file is copied into the image and included by the archive. Delete this and the notices
    are in the repository and in neither thing a client runs."""
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    copies = [
        line.split()
        for line in dockerfile.splitlines()
        if line.startswith("COPY") and NOTICES_PATH in line
    ]
    ignore = (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert any(words[-2:] == [NOTICES_PATH, f"/app/{NOTICES_PATH}"] for words in copies)
    assert f"!{NOTICES_PATH}" in ignore and "*.md" in ignore
    assert included_by(NOTICES_PATH)


def test_ci_runs_the_check_in_the_dependency_job() -> None:
    """The check is a step of the job that already reads every lock. Delete this and the file can
    go stale on a branch that never runs the unit suite's slice for it."""
    workflow = yaml.safe_load((REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    runs = [
        str(step.get("run", ""))
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ]

    assert any(re.search(r"brain\.ops\.third_party_notices check\s*$", one) for one in runs)


def test_a_dependency_cycle_in_a_lock_does_not_loop_and_a_shared_dependency_is_named_once() -> None:
    """Two packages that depend on each other, and one both reach. Delete this and the walk of the
    lock never ends on a cycle, or names a shared dependency twice."""
    lock = (
        'version = 1\n[[package]]\nname = "brain"\nversion = "0"\nsource = { editable = "." }\n'
        'dependencies = [{ name = "a" }, { name = "b" }]\n'
        '[[package]]\nname = "a"\nversion = "1"\nsource = { registry = "r" }\n'
        'dependencies = [{ name = "b" }, { name = "shared" }]\n'
        '[[package]]\nname = "b"\nversion = "1"\nsource = { registry = "r" }\n'
        'dependencies = [{ name = "a" }, { name = "shared" }]\n'
        '[[package]]\nname = "shared"\nversion = "1"\nsource = { registry = "r" }\n'
    )

    names = [one.name for one in python_shipped(lock, "uv.lock")]

    assert names == ["a", "b", "shared"]


def test_a_stale_file_ends_the_failure_with_the_one_command_that_regenerates_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Any lock change makes the check fail, for someone who did not write it. Delete this and the
    failure lists what is stale and says nothing of how to put it right."""
    monkeypatch.setattr("brain.ops.third_party_notices.check", lambda: ("pypi:x 1 ships",))

    assert main(["check"]) == 1
    printed = capsys.readouterr().out

    assert "pypi:x 1 ships" in printed
    assert REGENERATE_WITH in printed
    assert "third_party_notices write > NOTICES.md" in REGENERATE_WITH


def test_a_current_file_passes_without_the_regeneration_advice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The sibling: advice printed on success is noise a person learns to ignore. Delete this and
    the sentence can be printed on every run."""
    monkeypatch.setattr("brain.ops.third_party_notices.check", lambda: ())

    assert main(["check"]) == 0
    assert capsys.readouterr().out == ""
