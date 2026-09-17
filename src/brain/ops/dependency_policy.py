"""The dependency policy over every lock and every image, and the run that proves it refuses.

`brain.ops.sweeps dependencies` applies the licence allowlist to the environment one image
installed, and until 2026-09-17 it ended by printing "release age and archived checks need
network; enforced in CI". Nothing in CI enforced them: the job it named ran that same sweep. So
two of the three checks M0.5.7 names had never run anywhere, and the sentence saying where they
ran was the only trace of them.

**What this reads, and why each.** The two `uv.lock` files and the two `package-lock.json`
files, because a lock is what an image installs on every platform, where the installed
environment is one platform's subset (85 installed against 117 locked on the day this was
written). And every image a compose file or a Dockerfile names, because an install runs those
too and a licence nobody read on a container is still a licence the client runs under.

**The network half runs in CI only.** A licence read from the package index for the pinned
version, the date of the project's newest release, and whether its source repository is archived.
Every fetch is injected, so the rules are tested over fixed answers and the CI job is the one
place the real answers are asked. Rejected: a cache of those answers committed to the repository,
which is a second record that is right on the day it is written and silently stale after.

**Three outcomes, and only one is a pass.** A refusal fails the run. A component the owner has
not yet decided about is listed under `AWAITING_THE_OWNER` by name, never by licence, so a new
dependency under the same licence is still refused rather than quietly admitted. A component
with nothing readable is a note, the rule the licence sweep already has.

**The proof is a run, not a test.** `prove` copies the real application lock, adds a real GPL
package and a real package whose repository is archived, and requires both refused by the same
functions the audit calls, then requires the real locks and images to pass. Its evidence file is
what M0.7.1 asks to be recorded; see `THE_PROOF_ADDS_REAL_PACKAGES_NOT_INVENTED_ONES`.

Task ids: M0.5.7, M0.7.1
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from brain.ops.sweeps import declared_licence, licence_is_allowed

REPO = Path(__file__).resolve().parents[3]

#: The locks an image installs from. The matcher's is larger than the application's.
PYTHON_LOCKS: Final = ("uv.lock", "matcher/uv.lock")
NPM_LOCKS: Final = ("console/package-lock.json", "ops/automation/piece/package-lock.json")

#: A project whose newest release is older than this is refused, when it was chosen directly.
STALE_AFTER: Final = timedelta(days=3 * 365)

#: Why age refuses a direct dependency and only notes a transitive one.
AGE_REFUSES_WHAT_SOMEBODY_CHOSE: Final = (
    "A project with no release in three years is finished or abandoned, and the lock cannot tell "
    "which. For a dependency somebody named in a manifest that is a choice to revisit, so it "
    "refuses until the reason is written into REVIEWED_STALE. Measured on 2026-09-17, twenty-one "
    "transitive packages were past the line, most of them one-function libraries such as "
    "d3-ease and object-assign that are finished; refusing those would make the gate red for "
    "choices nobody here made and cannot change except by replacing the parent, so they are "
    "notes. Archived is different and refuses at any depth: an archived repository publishes no "
    "fix, whoever chose it."
)

#: Direct dependencies past `STALE_AFTER` that somebody has reviewed, with what they found.
REVIEWED_STALE: Final[Mapping[tuple[str, str], str]] = {}

#: Archived repositories somebody has reviewed, with what they found. Reviewed by the agent that
#: wrote this on 2026-09-17, not by the owner; replacing the parent removes the entry.
REVIEWED_ARCHIVED: Final[Mapping[tuple[str, str], str]] = {
    ("npm", "prop-types"): (
        "transitive through @rjsf/core, the console's form library; its checks are removed from "
        "a production build, and removing it means replacing the form library"
    ),
    ("npm", "require-from-string"): (
        "transitive through ajv, the console's JSON schema validator, which uses it only to load "
        "generated code; removing it means replacing the validator"
    ),
}


@dataclass(frozen=True)
class ImageTerms:
    """What running one image asks of an install."""

    licence: str
    #: True when production needs a paid key or a commercial licence to run it as configured.
    commercial_key: bool
    #: Where the licence was read, so a reviewer can check it rather than take it.
    read_from: str


#: Every image an install or a build pulls, by repository without its tag.
IMAGE_TERMS: Final[Mapping[str, ImageTerms]] = {
    "python": ImageTerms("PSF-2.0", False, "docker-library/python, the CPython licence"),
    "node": ImageTerms("MIT", False, "nodejs/node LICENSE"),
    "ghcr.io/astral-sh/uv": ImageTerms("MIT OR Apache-2.0", False, "astral-sh/uv LICENSE-*"),
    "mcr.microsoft.com/playwright/python": ImageTerms(
        "Apache-2.0", False, "microsoft/playwright-python LICENSE"
    ),
    "activepieces/activepieces": ImageTerms(
        "MIT", False, "activepieces LICENSE: community edition, no enterprise key is configured"
    ),
    "chrislusf/seaweedfs": ImageTerms("Apache-2.0", False, "seaweedfs LICENSE"),
    "clickhouse/clickhouse-server": ImageTerms("Apache-2.0", False, "ClickHouse LICENSE"),
    "cloudflare/cloudflared": ImageTerms("Apache-2.0", False, "cloudflared LICENSE"),
    "edoburu/pgbouncer": ImageTerms("ISC", False, "pgbouncer COPYRIGHT, the program it runs"),
    "langfuse/langfuse": ImageTerms(
        "MIT", False, "langfuse LICENSE: the ee directory needs a key and is not enabled"
    ),
    "langfuse/langfuse-worker": ImageTerms("MIT", False, "langfuse LICENSE, as above"),
    "openbao/openbao": ImageTerms("MPL-2.0", False, "openbao LICENSE"),
    "pgvector/pgvector": ImageTerms("PostgreSQL", False, "PostgreSQL and pgvector LICENSE"),
    "postgres": ImageTerms("PostgreSQL", False, "PostgreSQL COPYRIGHT"),
    "quay.io/keycloak/keycloak": ImageTerms("Apache-2.0", False, "keycloak LICENSE.txt"),
    "ubuntu/squid": ImageTerms("GPL-2.0-or-later", False, "squid COPYING"),
    "valkey/valkey": ImageTerms("BSD-3-Clause", False, "valkey COPYING"),
}

#: Components outside the allowlist that wait on a licence decision only the owner can make.
#: Keyed by component, never by licence, so a new dependency under one of these licences is
#: still refused. Each is printed on every run, so the list cannot be forgotten.
AWAITING_THE_OWNER: Final[Mapping[tuple[str, str], str]] = {
    ("image", "postgres"): "the PostgreSQL licence is permissive and is not on the allowlist",
    ("image", "pgvector/pgvector"): "the PostgreSQL licence, as above",
    ("image", "ubuntu/squid"): (
        "GPL-2.0-or-later, run unmodified in its own container as the automation egress proxy"
    ),
    ("npm", "@fontsource/ibm-plex-mono"): "OFL-1.1, a font licence, bundled into the console",
    ("npm", "@fontsource/ibm-plex-sans"): "OFL-1.1, as above",
    ("npm", "@fontsource/poppins"): "OFL-1.1, as above",
    ("pypi", "regex"): "Apache-2.0 AND CNRI-Python; CNRI-Python is permissive and not listed",
}


@dataclass(frozen=True)
class Component:
    """One thing an install runs or an image installs."""

    ecosystem: str
    name: str
    version: str
    where: str
    #: The licence the lock itself records, where it records one (npm does, uv does not).
    licence: str | None = None
    #: Named in a manifest here, rather than pulled in by something that was.
    direct: bool = False


@dataclass(frozen=True)
class Liveness:
    """What the package index and the source host say about one project."""

    licence: str | None
    last_release: datetime | None
    repository: str | None
    archived: bool | None


@dataclass
class Findings:
    refused: list[str] = field(default_factory=list)
    awaiting: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------------------ reading locks
def python_locked(text: str, where: str) -> tuple[Component, ...]:
    """Every registry package in a uv lock, less those an override removes on every platform.

    `matcher/uv.lock` still lists igraph, which splink declares and the matcher overrides to the
    marker `sys_platform == 'never'`. Reading it as installed would refuse a GPL package nothing
    installs; skipping every override would admit one that is only narrowed.
    """
    lock = tomllib.loads(text)
    never = {
        str(one["name"])
        for one in lock.get("manifest", {}).get("overrides", [])
        if str(one.get("marker", "")).replace('"', "'") == "sys_platform == 'never'"
    }
    packages = lock.get("package", [])
    direct: set[str] = set()
    for root in (one for one in packages if "registry" not in one.get("source", {})):
        groups = [root.get("dependencies", [])]
        groups += list(root.get("dev-dependencies", {}).values())
        groups += list(root.get("optional-dependencies", {}).values())
        direct.update(str(dep["name"]) for group in groups for dep in group)
    return tuple(
        Component(
            "pypi",
            str(package["name"]),
            str(package["version"]),
            where,
            direct=package["name"] in direct,
        )
        for package in packages
        if "registry" in package.get("source", {}) and package["name"] not in never
    )


def npm_locked(text: str, where: str) -> tuple[Component, ...]:
    """Every package a production install of this lock carries, with the licence npm recorded."""
    lock = json.loads(text)
    packages = lock.get("packages", {})
    direct = set(packages.get("", {}).get("dependencies", {}))
    found: list[Component] = []
    for path, package in sorted(packages.items()):
        if not path or package.get("dev") or "version" not in package:
            continue
        name = path.rsplit("node_modules/", 1)[-1]
        licence = str(package.get("license") or "") or None
        chosen = path == f"node_modules/{name}" and name in direct
        found.append(Component("npm", name, str(package["version"]), where, licence, chosen))
    return tuple(found)


_IMAGE_LINE_RE = re.compile(r"^\s*image:\s*[\"']?([^\s\"'#]+)", re.M)
_FROM_LINE_RE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", re.M | re.I)
_COPY_FROM_RE = re.compile(r"^\s*COPY\s+--from=(\S+)", re.M | re.I)


def repository_of(reference: str) -> str:
    """An image reference without its tag or digest."""
    bare = reference.split("@", 1)[0]
    last = bare.rsplit("/", 1)[-1]
    return bare[: len(bare) - len(last)] + last.split(":", 1)[0]


def images_in(repo: Path) -> tuple[Component, ...]:
    """Every literal image a compose file or a Dockerfile names.

    An image written as a variable is the product's own and is built here, so it is not a
    third party's terms. A `FROM` naming an earlier stage is that stage and not an image.
    """
    found: dict[tuple[str, str], Component] = {}
    for compose in sorted(repo.glob("docker-compose*.yml")):
        for reference in _IMAGE_LINE_RE.findall(compose.read_text(encoding="utf-8")):
            if "$" not in reference:
                image = Component("image", repository_of(reference), reference, compose.name)
                found.setdefault((image.name, reference), image)
    for dockerfile in sorted(p for p in repo.rglob("Dockerfile*") if "node_modules" not in p.parts):
        text = dockerfile.read_text(encoding="utf-8")
        stages = {alias.lower() for _, alias in _FROM_LINE_RE.findall(text) if alias}
        where = dockerfile.relative_to(repo).as_posix()
        references = [ref for ref, _ in _FROM_LINE_RE.findall(text)]
        references += _COPY_FROM_RE.findall(text)
        for reference in references:
            if reference.lower() in stages or "$" in reference or reference.isdigit():
                continue
            image = Component("image", repository_of(reference), reference, where)
            found.setdefault((image.name, reference), image)
    return tuple(found[key] for key in sorted(found))


def locked(repo: Path) -> tuple[Component, ...]:
    """Every component the policy judges: both ecosystems' locks and every image."""
    parts: list[Component] = []
    for name in PYTHON_LOCKS:
        parts.extend(python_locked((repo / name).read_text(encoding="utf-8"), name))
    for name in NPM_LOCKS:
        parts.extend(npm_locked((repo / name).read_text(encoding="utf-8"), name))
    parts.extend(images_in(repo))
    return tuple(parts)


# ------------------------------------------------------------------------------ the rules
def _label(component: Component) -> str:
    return f"{component.ecosystem}:{component.name} {component.version} ({component.where})"


def _judge_licence(component: Component, licence: str | None, into: Findings) -> None:
    key = (component.ecosystem, component.name)
    if not licence:
        into.notes.append(f"{_label(component)} declares no licence this can read")
    elif licence_is_allowed(licence):
        return
    elif key in AWAITING_THE_OWNER:
        into.awaiting.append(f"{_label(component)} is under {licence!r}: {AWAITING_THE_OWNER[key]}")
    else:
        into.refused.append(f"{_label(component)} is under {licence!r}, not on the allowlist")


def offline_findings(components: Iterable[Component]) -> Findings:
    """What can be judged with no network: licences a lock records, and every image's terms."""
    out = Findings()
    for component in components:
        if component.ecosystem == "npm":
            _judge_licence(component, component.licence, out)
        elif component.ecosystem == "image":
            terms = IMAGE_TERMS.get(component.name)
            if terms is None:
                out.refused.append(
                    f"{_label(component)} has no entry in IMAGE_TERMS, so nobody read its licence"
                )
                continue
            if terms.commercial_key:
                out.refused.append(f"{_label(component)} needs a commercial key in production")
            _judge_licence(component, terms.licence, out)
    return out


def liveness_findings(
    components: Iterable[Component], facts: Mapping[tuple[str, str], Liveness], *, now: datetime
) -> Findings:
    """Archived, stale, and for a uv lock the licence the index gives the pinned version."""
    out = Findings()
    for component in components:
        if component.ecosystem == "image":
            continue
        fact = facts.get((component.ecosystem, component.name))
        if fact is None:
            out.notes.append(f"{_label(component)}: the index gave no answer")
            continue
        if component.ecosystem == "pypi":
            _judge_licence(component, fact.licence, out)
        key = (component.ecosystem, component.name)
        if fact.archived and key in REVIEWED_ARCHIVED:
            out.notes.append(f"{_label(component)}: archived, reviewed: {REVIEWED_ARCHIVED[key]}")
        elif fact.archived:
            out.refused.append(f"{_label(component)}: its repository {fact.repository} is archived")
        elif fact.repository is None:
            out.notes.append(f"{_label(component)}: no source repository could be read")
        if fact.last_release is None:
            out.notes.append(f"{_label(component)}: no release date could be read")
        elif now - fact.last_release > STALE_AFTER and key not in REVIEWED_STALE:
            age = (now - fact.last_release).days
            if component.direct:
                out.refused.append(
                    f"{_label(component)}: no release for {age} days, and nobody has reviewed it"
                )
            else:
                out.notes.append(f"{_label(component)}: transitive, no release for {age} days")
    return out


# ------------------------------------------------------------------------------ the network
Fetch = Callable[[str], Any]
Archived = Callable[[str], bool | None]

_GITHUB_RE = re.compile(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")
_NOT_A_REPOSITORY_OWNER: Final = frozenset({"sponsors", "orgs", "users", "features", "apps"})


def github_repository(urls: Iterable[str]) -> str | None:
    """The first `owner/name` on GitHub among a project's links, skipping sponsor pages."""
    for url in urls:
        match = _GITHUB_RE.search(url or "")
        if match and match.group(1).lower() not in _NOT_A_REPOSITORY_OWNER:
            return f"{match.group(1)}/{match.group(2).removesuffix('.git')}"
    return None


def fetch_json(url: str) -> Any:
    # Only the two indexes' https addresses are ever built here; refusing anything else keeps
    # a `file:` URL from reading the runner's disk.
    if not url.startswith(("https://pypi.org/", "https://registry.npmjs.org/")):
        msg = f"not a package index address: {url}"
        raise ValueError(msg)
    request = urllib.request.Request(url, headers={"accept": "application/json"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.load(response)


def archived_on_github(repository: str) -> bool | None:
    """`gh api`, so the runner's token is read by gh and never by this process."""
    done = subprocess.run(  # noqa: S603  owner/name matched by _GITHUB_RE, no shell
        ["gh", "api", f"repos/{repository}", "--jq", ".archived"],  # noqa: S607  gh on PATH
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    answer = done.stdout.strip()
    return {"true": True, "false": False}.get(answer)


def _newest(stamps: Iterable[str]) -> datetime | None:
    parsed = [datetime.fromisoformat(one.replace("Z", "+00:00")) for one in stamps if one]
    return max(parsed) if parsed else None


def pypi_liveness(component: Component, fetch: Fetch, archived: Archived) -> Liveness:
    project = fetch(f"https://pypi.org/pypi/{component.name}/json")
    pinned = fetch(f"https://pypi.org/pypi/{component.name}/{component.version}/json")["info"]
    info = project["info"]
    stamps = [
        one.get("upload_time_iso_8601", "")
        for files in project["releases"].values()
        for one in files
    ]
    repository = github_repository(
        [*(info.get("project_urls") or {}).values(), info.get("home_page") or ""]
    )
    return Liveness(
        licence=declared_licence(
            pinned.get("license_expression"), pinned.get("license"), pinned.get("classifiers") or ()
        ),
        last_release=_newest(stamps),
        repository=repository,
        archived=archived(repository) if repository else None,
    )


def npm_liveness(component: Component, fetch: Fetch, archived: Archived) -> Liveness:
    document = fetch(f"https://registry.npmjs.org/{urllib.parse.quote(component.name, safe='@')}")
    times = {
        k: v for k, v in (document.get("time") or {}).items() if k not in {"created", "modified"}
    }
    source = document.get("repository") or {}
    url = source.get("url", "") if isinstance(source, Mapping) else str(source)
    repository = github_repository([url])
    return Liveness(
        licence=component.licence,
        last_release=_newest(times.values()),
        repository=repository,
        archived=archived(repository) if repository else None,
    )


def gather(
    components: Iterable[Component],
    fetch: Fetch = fetch_json,
    archived: Archived = archived_on_github,
) -> dict[tuple[str, str], Liveness]:
    """Every project's facts, asked once per project and eight at a time."""
    unique = {(c.ecosystem, c.name): c for c in components if c.ecosystem in {"pypi", "npm"}}

    def ask(component: Component) -> tuple[tuple[str, str], Liveness | None]:
        key = (component.ecosystem, component.name)
        try:
            ask_one = pypi_liveness if component.ecosystem == "pypi" else npm_liveness
            return key, ask_one(component, fetch, archived)
        except Exception:
            return key, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        answers = dict(pool.map(ask, unique.values()))
    return {key: fact for key, fact in answers.items() if fact is not None}


# ------------------------------------------------------------------------------ the proof
#: Why the proof's two additions are real packages.
THE_PROOF_ADDS_REAL_PACKAGES_NOT_INVENTED_ONES: Final = (
    "A package invented for the proof has whatever metadata the proof gave it, so refusing it "
    "proves the rule and nothing about the path that reads a real index. igraph 1.0.0 is GPL "
    "and declares it only as a classifier, which is the shape the licence check read as silence "
    "until 2026-09-17; oauth2client 4.1.3 is Apache-2.0 on a repository its owner archived, so "
    "only the archived check can refuse it."
)

COPYLEFT_ADDITION: Final = Component("pypi", "igraph", "1.0.0", "uv.lock + deliberate addition")
ARCHIVED_ADDITION: Final = Component(
    "pypi", "oauth2client", "4.1.3", "uv.lock + deliberate addition"
)


def with_addition(lock_text: str, addition: Component) -> str:
    """A copy of a uv lock with one more registry package in it, as `uv add` would leave it."""
    return (
        lock_text.rstrip("\n")
        + f'\n\n[[package]]\nname = "{addition.name}"\nversion = "{addition.version}"\n'
        + 'source = { registry = "https://pypi.org/simple" }\n'
    )


@dataclass(frozen=True)
class Proof:
    copyleft_refused: tuple[str, ...]
    archived_refused: tuple[str, ...]
    real: Findings
    components: int

    @property
    def holds(self) -> bool:
        return bool(self.copyleft_refused and self.archived_refused and not self.real.refused)


def prove(
    repo: Path, *, now: datetime, fetch: Fetch = fetch_json, archived: Archived = archived_on_github
) -> Proof:
    """Refuse the two deliberate additions, then pass the real locks and images."""
    base = (repo / PYTHON_LOCKS[0]).read_text(encoding="utf-8")
    real = locked(repo)
    facts = gather([*real, COPYLEFT_ADDITION, ARCHIVED_ADDITION], fetch, archived)

    def refusals_naming(addition: Component) -> tuple[str, ...]:
        doctored = python_locked(with_addition(base, addition), addition.where)
        found = liveness_findings(doctored, facts, now=now)
        return tuple(line for line in found.refused if f"pypi:{addition.name} " in line)

    judged = offline_findings(real)
    online = liveness_findings(real, facts, now=now)
    judged.refused.extend(online.refused)
    judged.awaiting.extend(online.awaiting)
    judged.notes.extend(online.notes)
    return Proof(
        refusals_naming(COPYLEFT_ADDITION), refusals_naming(ARCHIVED_ADDITION), judged, len(real)
    )


def evidence(proof: Proof, commit: str) -> dict[str, Any]:
    return {
        "commit": commit,
        "holds": proof.holds,
        "components_judged": proof.components,
        "deliberate_copyleft_addition_refused": list(proof.copyleft_refused),
        "deliberate_archived_addition_refused": list(proof.archived_refused),
        "real_refusals": proof.real.refused,
        "awaiting_the_owner": proof.real.awaiting,
        "notes": proof.real.notes,
        "images_needing_a_commercial_key": [
            name for name, terms in sorted(IMAGE_TERMS.items()) if terms.commercial_key
        ],
    }


def _print(found: Findings) -> None:
    for line in found.refused:
        print(f"refused: {line}")
    for line in found.awaiting:
        print(f"awaiting the owner: {line}")
    for line in found.notes:
        print(f"note: {line}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m brain.ops.dependency_policy")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("offline", help="licences the locks record and every image's terms")
    proving = sub.add_parser("prove", help="the network run: refuse two additions, pass the tree")
    proving.add_argument("--evidence", type=Path, required=True)
    proving.add_argument("--commit", default="unknown")
    arguments = parser.parse_args(argv)

    if arguments.command == "offline":
        found = offline_findings(locked(REPO))
        _print(found)
        print(f"{'FAIL' if found.refused else 'ok'}: offline dependency policy")
        return 1 if found.refused else 0

    proof = prove(REPO, now=datetime.now(UTC))
    _print(proof.real)
    print(f"deliberate copyleft addition refused: {list(proof.copyleft_refused)}")
    print(f"deliberate archived addition refused: {list(proof.archived_refused)}")
    arguments.evidence.parent.mkdir(parents=True, exist_ok=True)
    arguments.evidence.write_text(
        json.dumps(evidence(proof, arguments.commit), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"{'ok' if proof.holds else 'FAIL'}: the dependency policy proof over {proof.components}")
    return 0 if proof.holds else 1


if __name__ == "__main__":
    raise SystemExit(main())
