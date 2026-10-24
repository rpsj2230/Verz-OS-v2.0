"""The third-party notices file the image and the archive carry, and the check that it is not stale.

A product that bundles other people's software under licences that ask to be acknowledged has to
say so where the client finds it, and has to keep saying so after the next dependency bump. The
licence allowlist (`brain.ops.dependency_policy`) already judges every locked component in CI; what
it never produced was the thing the licences ask for, a list a client can read in the image they
run. This is that list, generated from the lockfiles and the images' declared terms and written to
`NOTICES.md` at the repository root, which the Dockerfile copies into the image and the release
archive includes.

**The committed file is the record and the check is offline.** Each Python package's licence is
read from the package index when the file is written (`write`), because `uv.lock` does not carry
one, and from the lock itself for the console's packages. `check` reads no network: it compares
the set of components the file names against the set the locks and compose files ship today, and
refuses a component missing from the file, one the file names that nothing ships, a version that
moved, and a shipped component with no licence recorded. So a dependency bump that does not
regenerate the file fails the unit suite and the dependency job, which is the leaf's "a release
missing one fails". Rejected: regenerating in CI and diffing, which needs the network on every run
and turns an index outage into a red build, and a file written at image build time, which a
person reading the repository could not see.

**What ships is the closure, not the lock.** `uv.lock` lists development packages too, and the
image installs `--no-dev`, so the Python set is what the project's own `dependencies` reach and
nothing a test runner pulled in. The console's lock marks `dev` packages itself. Fonts are npm
packages here (the `@fontsource` ones) and are listed like any other, which is where the font
licences the leaf names come from.

**What this does not do, and the question it leaves.** A notice here is a name, a version, a
licence identifier and where the project lives. It does not reproduce licence texts or copyright
lines, which are not in a lockfile and which some of the licences in use ask to be kept. Whether a
list satisfies the owner's obligation, or the release must carry each text, is a legal question
and is `docs/needs-rupash.md` item 268. Until it is answered the leaf is not claimed.

Task ids: M42.7.3
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from brain.ops.dependency_policy import (
    IMAGE_TERMS,
    NPM_LOCKS,
    PYTHON_LOCKS,
    REPO,
    Component,
    fetch_json,
    images_in,
    npm_locked,
)
from brain.ops.sweeps import declared_licence

#: Where the file lives, relative to the repository root. At the root, where a person looks first,
#: and named so the Dockerfile's copy and the archive's include rule are a literal each.
NOTICES_PATH: Final = "NOTICES.md"

#: The line every entry starts with, so the check reads entries and nothing a person wrote above.
ENTRY_PREFIX: Final = "- "

#: What a component with no readable licence is written as. The check refuses it for a shipped one.
NO_LICENCE: Final = "no licence declared"

#: Why the check is offline and the writer is not.
THE_FILE_IS_THE_RECORD_AND_THE_CHECK_NEEDS_NO_NETWORK: Final = (
    "A check that asked the package index on every run would turn an outage at the index into a "
    "red build and a release nobody could cut. So the licences are read when the file is written, "
    "by a person or by the dependency job's evidence run, and the check compares sets: what the "
    "locks ship today against what the file names."
)

#: Packages whose lock records no licence and whose project states one, read by a person.
#:
#: The two Activepieces framework packages are published from the community edition's repository,
#: which is MIT licensed (`brain.ops.dependency_policy.IMAGE_TERMS` records the same for its
#: image), and the registry entry simply omits the field. Named by package so a third package
#: with no licence is still refused, rather than a rule for "any package from that scope".
READ_FROM_THE_PROJECT: Final[Mapping[tuple[str, str], str]] = {
    ("npm", "@activepieces/pieces-framework"): "MIT",
    ("npm", "@activepieces/shared"): "MIT",
}

#: The ecosystem name an image is listed under.
IMAGE: Final = "image"


class NoticesError(Exception):
    """The file could not be produced as asked."""


@dataclass(frozen=True)
class Entry:
    """One line of the file: what ships, at which version, under which licence."""

    ecosystem: str
    name: str
    version: str
    licence: str
    where: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.ecosystem, self.name, self.version)


# -------------------------------------------------------------------- what ships
def python_shipped(text: str, where: str) -> tuple[Component, ...]:
    """The packages an image built with `--no-dev` installs from this uv lock.

    The closure of the project's own `dependencies` over the lock's `dependencies`, which is what
    `uv sync --no-dev` resolves, so a test runner and everything it pulled in is not named in a
    file a client reads as "what runs here".
    """
    lock = tomllib.loads(text)
    packages = {str(one["name"]): one for one in lock.get("package", [])}
    roots = [one for one in packages.values() if "registry" not in one.get("source", {})]
    seen: set[str] = set()
    pending = [str(dep["name"]) for root in roots for dep in root.get("dependencies", [])]
    while pending:
        name = pending.pop()
        if name in seen or name not in packages:
            continue
        seen.add(name)
        pending.extend(str(dep["name"]) for dep in packages[name].get("dependencies", []))
    return tuple(
        Component("pypi", name, str(packages[name]["version"]), where)
        for name in sorted(seen)
        if "registry" in packages[name].get("source", {})
    )


def shipped(repo: Path = REPO) -> tuple[Component, ...]:
    """Every component a release carries: runtime Python and npm packages, and every image."""
    parts: list[Component] = []
    for name in PYTHON_LOCKS:
        parts.extend(python_shipped((repo / name).read_text(encoding="utf-8"), name))
    for name in NPM_LOCKS:
        text = (repo / name).read_text(encoding="utf-8")
        parts.extend(one for one in npm_locked(text, name) if not one.build_only)
    parts.extend(images_in(repo))
    return tuple(parts)


# -------------------------------------------------------------------- the file
def _link(component: Component) -> str:
    if component.ecosystem == "pypi":
        return f"https://pypi.org/project/{component.name}/{component.version}/"
    if component.ecosystem == "npm":
        return f"https://www.npmjs.com/package/{component.name}/v/{component.version}"
    return ""


def render(entries: Iterable[Entry]) -> str:
    """The notices file for these entries, one line each, in an order that does not move."""
    distinct = {one.key: one for one in entries}
    ordered = sorted(
        distinct.values(), key=lambda one: (one.ecosystem, one.name.lower(), one.version)
    )
    lines = [
        "# Third-party notices",
        "",
        "This release bundles the software below. Each line is a component, the version this",
        "release carries, and the licence it is under; the project's own licence file at the",
        "address given is the authority. Generated by `brain.ops.third_party_notices` from the",
        "lockfiles and the images this release names: do not edit it, regenerate it.",
    ]
    heading = {
        "pypi": "Python packages",
        "npm": "Console packages and fonts",
        IMAGE: "Container images",
    }
    current = ""
    for one in ordered:
        if one.ecosystem != current:
            current = one.ecosystem
            lines.extend(("", f"## {heading.get(current, current)}", ""))
        link = _link(Component(one.ecosystem, one.name, one.version, one.where))
        tail = f" ({link})" if link else ""
        named = one.name if one.ecosystem == IMAGE else f"{one.name} {one.version}"
        lines.append(f"{ENTRY_PREFIX}{named}: {one.licence}{tail}")
    return "\n".join(lines).rstrip("\n") + "\n"


def parse(text: str) -> dict[tuple[str, str, str], str]:
    """Entries back out of a rendered file, as `(ecosystem, name, version) -> licence`.

    Reads the section headings the renderer writes and the entry lines under them, and nothing
    else, so prose above the first heading is not read as a component. An image has no version
    here: one repository can run at several tags, and the licence is the repository's.
    """
    reverse = {
        "Python packages": "pypi",
        "Console packages and fonts": "npm",
        "Container images": IMAGE,
    }
    ecosystem = ""
    found: dict[tuple[str, str, str], str] = {}
    for line in text.splitlines():
        if line.startswith("## "):
            ecosystem = reverse.get(line[3:].strip(), "")
            continue
        if not ecosystem or not line.startswith(ENTRY_PREFIX):
            continue
        head, _, rest = line[len(ENTRY_PREFIX) :].partition(": ")
        licence = rest.split(" (https://", 1)[0].strip()
        if ecosystem == IMAGE:
            found[(ecosystem, head.strip(), "")] = licence
            continue
        name, _, version = head.rpartition(" ")
        found[(ecosystem, name, version)] = licence
    return found


def check(repo: Path = REPO) -> tuple[str, ...]:
    """Every way the committed file differs from what this tree ships. Empty means it is current.

    Each finding is a fixed sentence about a kind of difference and names the component, which is
    the point: the person who bumped it is told which one. See
    `THE_FILE_IS_THE_RECORD_AND_THE_CHECK_NEEDS_NO_NETWORK`.
    """
    path = repo / NOTICES_PATH
    if not path.is_file():
        return (f"{NOTICES_PATH} does not exist, so the release carries no notice of anything",)
    held = parse(path.read_text(encoding="utf-8"))
    ships = {key_of(one) for one in shipped(repo)}
    gaps: list[str] = []
    for key in sorted(ships - held.keys()):
        gaps.append(f"{label(key)} ships and the notices file does not name it at this version")
    for key in sorted(held.keys() - ships):
        gaps.append(f"{label(key)} is in the notices file and nothing ships it")
    for key in sorted(ships & held.keys()):
        if not held[key] or held[key] == NO_LICENCE:
            gaps.append(f"{label(key)} is in the notices file with no licence recorded")
    return tuple(gaps)


def key_of(component: Component) -> tuple[str, str, str]:
    """How a shipped component is identified in the file: an image by repository alone."""
    version = "" if component.ecosystem == IMAGE else component.version
    return (component.ecosystem, component.name, version)


def label(key: tuple[str, str, str]) -> str:
    ecosystem, name, version = key
    return f"{ecosystem}:{name} {version}".rstrip()


# -------------------------------------------------------------------- writing it
def licences_for(
    components: Iterable[Component], fetch: Callable[[str], Any] = fetch_json
) -> dict[tuple[str, str], str]:
    """The licence each component is under: the lock for npm, the image table, the index for pypi.

    A package whose lock records none and which is named in `READ_FROM_THE_PROJECT` is given the
    licence that table states, with where it was read.
    """
    found: dict[tuple[str, str], str] = {}
    for one in components:
        key = (one.ecosystem, one.name)
        if one.ecosystem == "npm":
            found[key] = one.licence or READ_FROM_THE_PROJECT.get(key, NO_LICENCE)
        elif one.ecosystem == IMAGE:
            terms = IMAGE_TERMS.get(one.name)
            found[key] = terms.licence if terms is not None else NO_LICENCE
        else:
            info = fetch(f"https://pypi.org/pypi/{one.name}/{one.version}/json")["info"]
            found[key] = (
                declared_licence(
                    info.get("license_expression"),
                    info.get("license"),
                    info.get("classifiers") or (),
                    name=one.name,
                )
                or NO_LICENCE
            )
    return found


def entries_for(
    components: Sequence[Component], licences: Mapping[tuple[str, str], str]
) -> tuple[Entry, ...]:
    """One entry per distinct project and version, for the components that ship."""
    return tuple(
        Entry(
            one.ecosystem,
            one.name,
            "" if one.ecosystem == IMAGE else one.version,
            licences[(one.ecosystem, one.name)],
            one.where,
        )
        for one in components
    )


#: The sentence the check ends with when it fails, because any change to a lock file makes it fail
#: and the person who hits it is rarely the one who wrote it.
REGENERATE_WITH: Final = (
    "Regenerate the file with: uv run python -m brain.ops.third_party_notices write > NOTICES.md "
    "(it asks the package index for each licence), then commit it."
)


def write(repo: Path = REPO, fetch: Callable[[str], Any] = fetch_json) -> str:
    """The file's text for this tree, asking the package index for each Python licence."""
    components = shipped(repo)
    return render(entries_for(components, licences_for(components, fetch)))


def main(argv: Sequence[str] | None = None) -> int:
    """`check` is offline; `write` asks the package index and prints the file."""
    parser = argparse.ArgumentParser(prog="python -m brain.ops.third_party_notices")
    parser.add_argument("command", choices=("check", "write"))
    arguments = parser.parse_args(argv)
    if arguments.command == "write":
        sys.stdout.write(write())
        return 0
    gaps = check()
    for gap in gaps:
        print(gap)
    if gaps:
        print(REGENERATE_WITH)
    return 1 if gaps else 0


if __name__ == "__main__":  # pragma: no cover - the command that writes the committed file
    raise SystemExit(main())
