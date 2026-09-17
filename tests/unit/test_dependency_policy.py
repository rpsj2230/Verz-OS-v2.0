"""The dependency policy over every lock and image, judged over fixed answers from the index.

The network is asked only by CI's `Dependency audit` job; every test here hands the rules fixed
facts, so what is tested is the decision and not whether PyPI answered today.

Task ids: M0.5.7, M0.7.1
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.ops import dependency_policy as policy
from brain.ops.dependency_policy import (
    ARCHIVED_ADDITION,
    COPYLEFT_ADDITION,
    IMAGE_TERMS,
    STALE_AFTER,
    Component,
    ImageTerms,
    Liveness,
    github_repository,
    images_in,
    liveness_findings,
    locked,
    npm_locked,
    offline_findings,
    prove,
    python_locked,
    repository_of,
    with_addition,
)
from brain.ops.sweeps import declared_licence

REPO = Path(__file__).resolve().parents[2]

#: Far from any wall clock, so no fixture here goes off on a date nobody chose.
NOW = datetime(2999, 1, 1, tzinfo=UTC)
FRESH = NOW - timedelta(days=30)

LOCK = """version = 1

[manifest]
overrides = [{ name = "igraph", marker = "sys_platform == 'never'" }]

[[package]]
name = "app"
version = "0.1.0"
source = { editable = "." }
dependencies = [{ name = "chosen" }]

[package.dev-dependencies]
dev = [{ name = "tooling" }]

[[package]]
name = "chosen"
version = "1.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "pulled-in"
version = "2.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "tooling"
version = "3.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "igraph"
version = "1.0.0"
source = { registry = "https://pypi.org/simple" }
"""


def alive(licence: str = "MIT", *, released: datetime = FRESH) -> Liveness:
    return Liveness(licence, released, "owner/project", archived=False)


# ------------------------------------------------------------------------------ reading locks
def test_a_uv_lock_is_read_as_every_registry_package_less_what_an_override_removes() -> None:
    """igraph is in the matcher's real lock and overridden to a platform that never exists. Delete
    this and the policy either refuses a GPL package nothing installs, which makes the audit red
    for ever, or somebody drops overrides altogether and admits one that is only narrowed."""
    names = {c.name: c.direct for c in python_locked(LOCK, "uv.lock")}
    assert names == {"chosen": True, "pulled-in": False, "tooling": True}


def test_an_override_to_a_real_platform_does_not_remove_the_package() -> None:
    """The sibling: only the `never` marker removes. Delete this and an override that narrows a
    package to Linux, which is where the image runs, hides it from the licence check."""
    narrowed = LOCK.replace("sys_platform == 'never'", "sys_platform == 'linux'")
    assert "igraph" in {c.name for c in python_locked(narrowed, "uv.lock")}


def test_an_npm_lock_carries_production_packages_with_their_recorded_licence() -> None:
    """Development packages never reach the console bundle. Delete this and a dev-only GPL test
    runner refuses the build, or a nested copy of a direct dependency is counted as chosen."""
    lock = {
        "packages": {
            "": {"dependencies": {"left": "1.0.0"}},
            "node_modules/left": {"version": "1.0.0", "license": "MIT"},
            "node_modules/left/node_modules/left": {"version": "0.9.0", "license": "MIT"},
            "node_modules/runner": {"version": "2.0.0", "license": "GPL-3.0-only", "dev": True},
            "node_modules/nameless": {"version": "1.0.0"},
        }
    }
    found = npm_locked(json.dumps(lock), "console/package-lock.json")
    assert [(c.name, c.version, c.licence, c.direct) for c in found] == [
        ("left", "1.0.0", "MIT", True),
        ("left", "0.9.0", "MIT", False),
        ("nameless", "1.0.0", None, False),
    ]


@pytest.mark.parametrize(
    ("reference", "repository"),
    [
        ("postgres:18-alpine", "postgres"),
        ("quay.io/keycloak/keycloak:26.0", "quay.io/keycloak/keycloak"),
        ("ghcr.io/astral-sh/uv:0.12.9", "ghcr.io/astral-sh/uv"),
        ("localhost:5000/thing:1", "localhost:5000/thing"),
        ("python@sha256:abc", "python"),
    ],
)
def test_an_image_reference_is_its_repository_without_the_tag(
    reference: str, repository: str
) -> None:
    """A registry with a port has a colon before the tag. Delete this and `localhost:5000/thing`
    is looked up as `localhost`, which has no terms and refuses, or matches the wrong entry."""
    assert repository_of(reference) == repository


def test_every_image_this_repository_names_is_found_and_has_terms() -> None:
    """The real tree. Delete this and an image added to a compose file or a Dockerfile, including
    a build stage's `COPY --from`, runs on installs under terms nobody read."""
    found = {c.name for c in images_in(REPO)}
    assert {"python", "node", "ghcr.io/astral-sh/uv", "postgres", "ubuntu/squid"} <= found
    assert "console" not in found, "a build stage was read as an image"
    assert found <= set(IMAGE_TERMS), sorted(found - set(IMAGE_TERMS))


# ------------------------------------------------------------------------------ licences
def test_a_gpl_licence_stated_only_in_free_text_is_a_declaration_and_is_refused() -> None:
    """igraph 1.0.0's real metadata: no expression, no classifier, and 'GNU General Public License
    (GPL)' in the free-text field. Until 2026-09-17 that read as declaring nothing, which is a
    note, so the one licence the allowlist exists to refuse passed it. Delete this and it does
    again."""
    declared = declared_licence(None, "GNU General Public License (GPL)", ())
    component = Component("pypi", "igraph", "1.0.0", "uv.lock")
    found = liveness_findings([component], {("pypi", "igraph"): alive(declared)}, now=NOW)
    assert len(found.refused) == 1 and "not on the allowlist" in found.refused[0]


def test_a_gpl_classifier_is_a_declaration_too() -> None:
    """The classifier half of the same rule, for installed metadata. Delete this and a package
    whose only licence metadata is `GPLv2+` is a note in the installed sweep."""
    classifier = "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)"
    assert declared_licence(None, None, [classifier]) == classifier


def test_a_permissive_package_is_not_caught_by_the_copyleft_reading() -> None:
    """The positive case: a mapped classifier and an allowed free-text id still read as themselves.
    Delete this and the copyleft rule can swallow every classifier and still pass the two above."""
    assert declared_licence(None, "MIT", ()) == "MIT"
    assert declared_licence(None, "", ["License :: OSI Approved :: MIT License"]) == "MIT"
    assert declared_licence(None, "Apache 2.0", ()) == ""


def test_an_npm_package_under_an_allowed_licence_passes_and_one_outside_is_refused() -> None:
    """Delete this and the npm half of the audit can refuse everything or nothing."""
    good = Component("npm", "left", "1.0.0", "lock", "MIT")
    bad = Component("npm", "copyleft", "1.0.0", "lock", "GPL-3.0-only")
    found = offline_findings([good, bad])
    assert found.refused == [
        "npm:copyleft 1.0.0 (lock) is under 'GPL-3.0-only', not on the allowlist"
    ]


def test_a_decision_the_owner_has_not_made_is_named_by_component_not_by_licence() -> None:
    """The fonts wait on the owner. A second package under the same font licence must still be
    refused. Delete this and somebody keys the table by licence, and every OFL package after it
    is admitted by a decision nobody took."""
    waiting = Component("npm", "@fontsource/poppins", "5.2.7", "lock", "OFL-1.1")
    newcomer = Component("npm", "another-font", "1.0.0", "lock", "OFL-1.1")
    found = offline_findings([waiting, newcomer])
    assert len(found.awaiting) == 1 and "@fontsource/poppins" in found.awaiting[0]
    assert len(found.refused) == 1 and "another-font" in found.refused[0]


def test_an_image_with_no_terms_or_needing_a_commercial_key_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M0.7.1's last clause. Delete this and an image that needs a paid key in production ships
    because its licence text happened to be permissive."""
    monkeypatch.setitem(
        policy.IMAGE_TERMS, "vendor/enterprise", ImageTerms("Apache-2.0", True, "vendor terms")
    )
    keyed = Component("image", "vendor/enterprise", "vendor/enterprise:1", "compose")
    unknown = Component("image", "vendor/unknown", "vendor/unknown:1", "compose")
    fine = Component("image", "valkey/valkey", "valkey/valkey:8", "compose")
    found = offline_findings([keyed, unknown, fine])
    assert any("commercial key" in line and "enterprise" in line for line in found.refused)
    assert any("no entry in IMAGE_TERMS" in line and "unknown" in line for line in found.refused)
    assert not any("valkey" in line for line in found.refused)


def test_no_image_on_the_list_needs_a_commercial_key() -> None:
    """Asserted over the table rather than over a flag the proof reads. Delete this and one entry
    set to True is a finding only on a run nobody opens."""
    assert [name for name, terms in IMAGE_TERMS.items() if terms.commercial_key] == []


def test_the_real_tree_passes_the_offline_policy() -> None:
    """Delete this and the job goes red on arrival for a component the table forgot."""
    assert offline_findings(locked(REPO)).refused == []


# ------------------------------------------------------------------------------ liveness
def test_an_archived_repository_is_refused_at_any_depth() -> None:
    """Delete this and a dependency whose repository will never publish a fix ships silently."""
    component = Component("pypi", "oauth2client", "4.1.3", "uv.lock", direct=False)
    fact = Liveness("Apache-2.0", FRESH, "google/oauth2client", archived=True)
    found = liveness_findings([component], {("pypi", "oauth2client"): fact}, now=NOW)
    assert found.refused == [
        "pypi:oauth2client 4.1.3 (uv.lock): its repository google/oauth2client is archived"
    ]


def test_an_archived_repository_somebody_reviewed_is_a_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sibling. Delete this and the review list can be ignored, and the two reviewed console
    dependencies make the audit red until the form library is replaced."""
    monkeypatch.setitem(policy.REVIEWED_ARCHIVED, ("npm", "old"), "reviewed")
    component = Component("npm", "old", "1.0.0", "lock", "MIT")
    fact = Liveness("MIT", FRESH, "someone/old", archived=True)
    found = liveness_findings([component], {("npm", "old"): fact}, now=NOW)
    assert found.refused == [] and any("reviewed" in line for line in found.notes)


def test_age_refuses_a_direct_dependency_and_notes_a_transitive_one() -> None:
    """See `AGE_REFUSES_WHAT_SOMEBODY_CHOSE`. Delete this and the age check is either a note
    nobody reads for a choice somebody made, or red for twenty finished micro-libraries."""
    stale = NOW - STALE_AFTER - timedelta(days=1)
    chosen = Component("pypi", "chosen", "1.0", "uv.lock", direct=True)
    pulled = Component("pypi", "pulled", "1.0", "uv.lock", direct=False)
    facts = {("pypi", "chosen"): alive(released=stale), ("pypi", "pulled"): alive(released=stale)}
    found = liveness_findings([chosen, pulled], facts, now=NOW)
    assert len(found.refused) == 1 and "pypi:chosen" in found.refused[0]
    assert any("pypi:pulled" in line and "transitive" in line for line in found.notes)


def test_a_direct_dependency_just_inside_the_line_passes() -> None:
    """The boundary. Delete this and `>` becoming `>=` or the line moving to a day passes."""
    inside = NOW - STALE_AFTER + timedelta(days=1)
    chosen = Component("pypi", "chosen", "1.0", "uv.lock", direct=True)
    assert (
        liveness_findings([chosen], {("pypi", "chosen"): alive(released=inside)}, now=NOW).refused
        == []
    )
    assert timedelta(days=1000) < STALE_AFTER < timedelta(days=1200)


@pytest.mark.parametrize(
    ("urls", "repository"),
    [
        (
            ["https://github.com/sponsors/hynek", "https://github.com/hynek/structlog"],
            "hynek/structlog",
        ),
        (["http://github.com/google/oauth2client/"], "google/oauth2client"),
        (["git+https://github.com/facebook/prop-types.git"], "facebook/prop-types"),
        (["https://example.org"], None),
    ],
)
def test_a_projects_repository_is_read_past_sponsor_pages(
    urls: list[str], repository: str | None
) -> None:
    """structlog's first GitHub link is its sponsor page. Delete this and the archived check asks
    about `sponsors/hynek`, gets no answer, and a real archived repository reads as unknown."""
    assert github_repository(urls) == repository


# ------------------------------------------------------------------------------ the proof
def _index(archived: set[str], licences: dict[str, str]) -> tuple[Any, Any]:
    def fetch(url: str) -> Any:
        name = url.split("/pypi/", 1)[1].split("/")[0] if "/pypi/" in url else url.rsplit("/", 1)[1]
        info: dict[str, Any] = {
            "license_expression": None,
            "license": licences.get(name, "MIT"),
            "classifiers": [],
            "project_urls": {"Source": f"https://github.com/owner/{name}"},
            "home_page": "",
        }
        if "registry.npmjs.org" in url:
            return {"time": {"1.0.0": FRESH.isoformat()}, "repository": {"url": ""}}
        return {"info": info, "releases": {"1": [{"upload_time_iso_8601": FRESH.isoformat()}]}}

    def is_archived(repository: str) -> bool | None:
        return repository.split("/", 1)[1] in archived

    return fetch, is_archived


def test_the_proof_holds_when_both_additions_are_refused_and_the_tree_passes() -> None:
    """M0.7.1's run, over a fixed index. Delete this and `prove` can report success without the
    additions having reached the rules the audit applies to the real tree."""
    fetch, is_archived = _index({"oauth2client"}, {"igraph": "GNU General Public License (GPL)"})
    proof = prove(REPO, now=NOW, fetch=fetch, archived=is_archived)
    assert proof.copyleft_refused and "pypi:igraph" in proof.copyleft_refused[0]
    assert proof.archived_refused and "archived" in proof.archived_refused[0]
    assert proof.real.refused == []
    assert proof.holds


def test_the_proof_fails_when_the_index_does_not_answer() -> None:
    """A network outage must not read as a pass. Delete this and a run that reached nothing
    refuses nothing, and a policy that refuses nothing looks exactly like a clean tree."""

    def nothing(url: str) -> Any:
        raise OSError("unreachable")

    proof = prove(REPO, now=NOW, fetch=nothing, archived=lambda repository: None)
    assert not proof.holds


def test_the_additions_are_the_real_packages_the_constant_names() -> None:
    """See `THE_PROOF_ADDS_REAL_PACKAGES_NOT_INVENTED_ONES`. Delete this and the additions can be
    renamed to packages that do not exist, which the index refuses for a reason that is not the
    rule under proof."""
    assert (COPYLEFT_ADDITION.name, COPYLEFT_ADDITION.version) == ("igraph", "1.0.0")
    assert (ARCHIVED_ADDITION.name, ARCHIVED_ADDITION.version) == ("oauth2client", "4.1.3")
    doctored = python_locked(with_addition(LOCK, ARCHIVED_ADDITION), "x")
    assert ("oauth2client", "4.1.3") in {(c.name, c.version) for c in doctored}


def test_ci_runs_the_offline_policy_and_the_proof_and_keeps_the_evidence() -> None:
    """The recorded run M0.7.1 asks for. Delete this and the step can be removed and the proof
    exists only as a function nobody calls."""
    workflow = yaml.safe_load(
        (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["supply_chain"]["steps"]
    runs = [" ".join(str(step.get("run", "")).split()) for step in steps]
    assert "uv run python -m brain.ops.dependency_policy offline" in runs
    proof = next(step for step in steps if "dependency_policy prove" in str(step.get("run", "")))
    assert "--evidence evidence/dependency-policy.json" in " ".join(str(proof["run"]).split())
    assert proof["env"]["GH_TOKEN"] == "${{ github.token }}"
    kept = [step for step in steps if step.get("uses", "").startswith("actions/upload-artifact")]
    assert any(step["with"]["path"] == "evidence/dependency-policy.json" for step in kept)


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "http://pypi.org/pypi/x/json", "https://pypi.org.evil/x"]
)
def test_the_fetcher_refuses_anything_but_the_two_indexes(url: str) -> None:
    """Delete this and the scheme check that keeps a `file:` URL off the runner's disk can go
    with nothing noticing; no network is touched, the refusal comes first."""
    with pytest.raises(ValueError, match="not a package index address"):
        policy.fetch_json(url)
