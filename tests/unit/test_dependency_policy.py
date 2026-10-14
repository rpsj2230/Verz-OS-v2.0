"""The dependency policy over every lock and image, judged over fixed answers from the index.

The network is asked only by CI's `Dependency audit` job; every test here hands the rules fixed
facts, so what is tested is the decision and not whether PyPI answered today.

Task ids: M0.5.7, M0.7.1, M27.15.79
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
    BUILD_ONLY_AWAITING_THE_OWNER,
    COPYLEFT_ADDITION,
    IMAGE_TERMS,
    NPM_LOCKS,
    OWNER_ALLOWED,
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
from brain.ops.sweeps import declared_licence, licence_is_allowed

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


def test_an_npm_lock_carries_every_package_with_its_licence_and_marks_the_build_only_ones() -> None:
    """**M27.15.79.** A package npm marks `dev` is read, with its licence, and flagged build-only.
    Until this leaf it was dropped, so 240 of the console lock's 387 packages were never judged.
    Delete this and a development package slips back out of the audit, or a nested copy of a
    direct dependency is counted as chosen."""
    lock = {
        "packages": {
            "": {"dependencies": {"left": "1.0.0"}},
            "node_modules/left": {"version": "1.0.0", "license": "MIT"},
            "node_modules/left/node_modules/left": {"version": "0.9.0", "license": "MIT"},
            "node_modules/runner": {"version": "2.0.0", "license": "GPL-3.0-only", "dev": True},
            "node_modules/nameless": {"version": "1.0.0"},
            "node_modules/linked": {"link": True, "resolved": "../linked"},
        }
    }
    found = npm_locked(json.dumps(lock), "console/package-lock.json")
    assert [(c.name, c.version, c.licence, c.direct, c.build_only) for c in found] == [
        ("left", "1.0.0", "MIT", True, False),
        ("left", "0.9.0", "MIT", False, False),
        ("nameless", "1.0.0", None, False, False),
        ("runner", "2.0.0", "GPL-3.0-only", False, True),
    ]


def _console(packages: dict[str, dict[str, Any]]) -> list[Component]:
    """A console lock with these packages in it, read as the policy reads the real one."""
    lock = {"packages": {"": {"dependencies": {}}, **packages}}
    return list(npm_locked(json.dumps(lock), "console/package-lock.json"))


@pytest.mark.parametrize(
    ("licence", "allowed"),
    [
        ("MIT", True),
        ("MIT OR Apache-2.0", True),
        ("(MIT OR CC0-1.0)", True),
        ("MIT AND GPL-3.0-only", False),
        ("GPL-3.0-only OR AGPL-3.0-only", False),
        ("SEE LICENSE IN LICENSE.md", False),
        ("UNLICENSED", False),
        ("Apache-2.0 WITH LLVM-exception", False),
        ("(MIT", False),
    ],
)
def test_a_console_package_is_judged_on_the_spdx_expression_its_lock_row_records(
    licence: str, allowed: bool
) -> None:
    """**M27.15.79.** One shipped console package per licence expression, read through the same
    reader the real lock goes through: OR is a choice, AND needs every term, and a licence the
    list does not name, a pointer to a file and a broken bracket are all refusals. Delete this and
    the console half of the audit can be satisfied by a reader that admits everything, or by one
    that refuses `MIT OR Apache-2.0`."""
    found = offline_findings(_console({"node_modules/p": {"version": "1.0.0", "license": licence}}))
    assert (found.refused == []) is allowed
    assert found.awaiting == []


def test_a_console_package_with_no_licence_in_the_lock_is_refused_but_another_lock_only_notes() -> (
    None
):
    """**M27.15.79.** The leaf is every console dependency, so a lock row naming no licence is a
    refusal for the console's lock and stays a note for the automation piece's, which has two such
    packages today. Delete this and a console package that records no licence passes as a note
    nobody reads."""
    bare = {"node_modules/p": {"version": "1.0.0"}}
    console = offline_findings(_console(bare))
    assert len(console.refused) == 1 and "records no licence" in console.refused[0]
    piece = npm_locked(
        json.dumps({"packages": {"": {}, **bare}}), "ops/automation/piece/package-lock.json"
    )
    found = offline_findings(piece)
    assert found.refused == [] and len(found.notes) == 1
    assert "console/package-lock.json" in policy.LOCKS_WHERE_NO_LICENCE_REFUSES


def test_a_build_only_package_outside_the_list_is_refused_unless_it_waits_on_the_owner() -> None:
    """**M27.15.79.** The failing case the leaf asks for: a development dependency under a copyleft
    licence is refused, exactly as a shipped one is. The three that wait on the owner are listed
    by name and by licence, and the same name under another licence is refused again. Delete this
    and a GPL test runner is admitted because it never ships, or a waiting package is admitted
    under any licence."""
    copyleft = _console(
        {"node_modules/runner": {"version": "2.0.0", "license": "GPL-3.0-only", "dev": True}}
    )
    refused = offline_findings(copyleft).refused
    assert len(refused) == 1 and "'GPL-3.0-only', not on the allowlist" in refused[0]
    waiting = _console(
        {"node_modules/caniuse-lite": {"version": "1", "license": "CC-BY-4.0", "dev": True}}
    )
    found = offline_findings(waiting)
    assert found.refused == [] and len(found.awaiting) == 1
    relicensed = _console(
        {"node_modules/caniuse-lite": {"version": "2", "license": "GPL-3.0-only", "dev": True}}
    )
    assert len(offline_findings(relicensed).refused) == 1
    shipped = _console({"node_modules/caniuse-lite": {"version": "1", "license": "CC-BY-4.0"}})
    assert len(offline_findings(shipped).refused) == 1, "a shipped package never waits"


def test_a_build_only_package_is_never_judged_for_age_or_an_archived_repository() -> None:
    """**M27.15.79.** The sibling of the refusal above: what ships is held to the liveness rules
    and what only compiles it is not, so an archived test-runner helper does not turn the audit
    red. Delete this and the 240 development packages add refusals nobody can act on, or the
    exemption leaks to a shipped package."""
    dev = Component("npm", "helper", "1.0.0", "lock", "MIT", build_only=True)
    shipped = Component("npm", "helper", "1.0.0", "lock", "MIT")
    archived = Liveness("MIT", FRESH, "owner/helper", archived=True)
    assert liveness_findings([dev], {("npm", "helper"): archived}, now=NOW).refused == []
    assert len(liveness_findings([shipped], {("npm", "helper"): archived}, now=NOW).refused) == 1
    asked: list[str] = []

    def fetch(url: str) -> Any:
        asked.append(url)
        return {"time": {"1": FRESH.isoformat()}, "repository": {"url": ""}}

    policy.gather([dev], fetch=fetch, archived=lambda _: False)
    assert asked == []
    policy.gather([shipped], fetch=fetch, archived=lambda _: False)
    assert len(asked) == 1


def test_every_package_in_the_real_console_lock_is_judged_and_the_list_is_the_owners() -> None:
    """**M27.15.79.** Over the real lock: every package it records is read (none dropped for being
    development), every one carries a licence, and the licences found outside the allowed list are
    exactly the owner's three fonts and the three build-only packages waiting on him, so the list
    has not been widened to make the audit pass. Delete this and a widened allowlist, or a package
    dropped from the reader, goes unseen."""
    from brain.ops.sweeps import ALLOWED_LICENCES

    text = (REPO / "console" / "package-lock.json").read_text(encoding="utf-8")
    recorded = {
        path.rsplit("node_modules/", 1)[-1] + "@" + str(row["version"])
        for path, row in json.loads(text)["packages"].items()
        if path and "version" in row
    }
    console = npm_locked(text, "console/package-lock.json")
    assert {f"{one.name}@{one.version}" for one in console} == recorded
    assert any(one.build_only for one in console) and any(not one.build_only for one in console)
    assert all(one.licence for one in console)
    outside = {one.name: one.licence for one in console if one.licence not in ALLOWED_LICENCES}
    judged = offline_findings(console)
    assert judged.refused == []
    assert {name for name, licence in outside.items() if not licence_is_allowed(str(licence))} == {
        "@fontsource/ibm-plex-mono",
        "@fontsource/ibm-plex-sans",
        "@fontsource/poppins",
        "argparse",
        "caniuse-lite",
        "lru-cache",
    }
    assert {
        "MIT",
        "MIT-0",
        "0BSD",
        "Zlib",
        "CC0-1.0",
        "Apache-2.0",
        "BSD-3-Clause",
        "BSD-2-Clause",
        "ISC",
        "PSF-2.0",
        "MPL-2.0",
        "LGPL-3.0-only",
        "LGPL-3.0-or-later",
    } == ALLOWED_LICENCES


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


LGPLV3_CLASSIFIER = "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)"


def test_ldap3s_classifier_reads_as_the_licence_its_source_grants_and_for_ldap3_alone() -> None:
    """Item 93 (M1.6.6). ldap3 2.9.1's real metadata: no expression, "LGPL v3" as free text and
    the LGPLv3 classifier, which names neither -only nor -or-later. It is read as the or-later
    its source headers grant, for ldap3 by name; any other package carrying that classifier is
    still the classifier text, and refused. Delete this and either the owner's decision refuses
    the library he allowed, or the classifier admits every LGPL package after it unread."""
    assert declared_licence(None, "LGPL v3", [LGPLV3_CLASSIFIER], name="ldap3") == (
        "LGPL-3.0-or-later"
    )
    assert declared_licence(None, "LGPL v3", [LGPLV3_CLASSIFIER], name="another") == (
        LGPLV3_CLASSIFIER
    )
    assert declared_licence(None, "LGPL v3", [LGPLV3_CLASSIFIER]) == LGPLV3_CLASSIFIER
    ours = Component("pypi", "ldap3", "2.9.1", "uv.lock", direct=True)
    stranger = Component("pypi", "another", "1.0.0", "uv.lock", direct=True)
    found = liveness_findings(
        [ours, stranger],
        {
            ("pypi", "ldap3"): alive("LGPL-3.0-or-later"),
            ("pypi", "another"): alive(LGPLV3_CLASSIFIER),
        },
        now=NOW,
    )
    assert len(found.refused) == 1 and "another" in found.refused[0]


def test_an_npm_package_under_an_allowed_licence_passes_and_one_outside_is_refused() -> None:
    """Delete this and the npm half of the audit can refuse everything or nothing."""
    good = Component("npm", "left", "1.0.0", "lock", "MIT")
    bad = Component("npm", "copyleft", "1.0.0", "lock", "GPL-3.0-only")
    found = offline_findings([good, bad])
    assert found.refused == [
        "npm:copyleft 1.0.0 (lock) is under 'GPL-3.0-only', not on the allowlist"
    ]


def test_a_decision_the_owner_has_not_made_is_named_by_component_not_by_licence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A waiting component is listed; a second package under the same licence must still be
    refused. Delete this and somebody keys the table by licence, and every package after it is
    admitted by a decision nobody took."""
    monkeypatch.setitem(policy.AWAITING_THE_OWNER, ("npm", "waiting-font"), "OFL-1.1")
    waiting = Component("npm", "waiting-font", "1.0.0", "lock", "OFL-1.1")
    newcomer = Component("npm", "another-font", "1.0.0", "lock", "OFL-1.1")
    found = offline_findings([waiting, newcomer])
    assert len(found.awaiting) == 1 and "waiting-font" in found.awaiting[0]
    assert len(found.refused) == 1 and "another-font" in found.refused[0]


def test_the_owners_eight_licence_decisions_pass_and_admit_nothing_else() -> None:
    """Items 70 (M0.7.1) and 93 (M1.6.6): the owner allowed exactly these eight components.
    Delete this and the GPL squid entry can become a GPL entry for anything, or a font licence
    for any font."""
    assert set(OWNER_ALLOWED) == {
        ("image", "postgres"),
        ("image", "pgvector/pgvector"),
        ("image", "ubuntu/squid"),
        ("npm", "@fontsource/ibm-plex-mono"),
        ("npm", "@fontsource/ibm-plex-sans"),
        ("npm", "@fontsource/poppins"),
        ("pypi", "regex"),
        ("pypi", "ldap3"),
    }
    assert all(
        "needs-rupash item 70" in one.reason or "needs-rupash item 93" in one.reason
        for one in OWNER_ALLOWED.values()
    )
    allowed = [
        Component("npm", "@fontsource/poppins", "5.2.7", "lock", "OFL-1.1"),
        Component("image", "ubuntu/squid", "ubuntu/squid:6", "compose"),
        Component("image", "postgres", "postgres:17", "compose"),
    ]
    found = offline_findings(allowed)
    assert found.refused == [] and found.awaiting == []
    others = [
        Component("npm", "another-font", "1.0.0", "lock", "OFL-1.1"),
        Component("npm", "gpl-thing", "1.0.0", "lock", "GPL-2.0-or-later"),
    ]
    assert len(offline_findings(others).refused) == 2


def test_an_owner_allowed_component_under_a_new_licence_is_refused_again() -> None:
    """The decision is pinned to the licence he read. Delete this and a relicensed release of
    an allowed package (say, to AGPL) ships on a decision about a different licence."""
    relicensed = Component("npm", "@fontsource/poppins", "9.0.0", "lock", "AGPL-3.0-only")
    found = offline_findings([relicensed])
    assert len(found.refused) == 1 and "allowed it under 'OFL-1.1' only" in found.refused[0]
    component = Component("pypi", "regex", "2026.9.3", "uv.lock")
    ok = liveness_findings(
        [component], {("pypi", "regex"): alive(licence="Apache-2.0 AND CNRI-Python")}, now=NOW
    )
    assert ok.refused == [] and ok.awaiting == []


def test_the_only_components_awaiting_the_owner_are_the_three_build_only_ones() -> None:
    """Item 70 decided every shipped component, and three packages that only the build and the
    test runner use wait on item 236. Delete this and a fourth wait, or one of these three
    shipping, goes unnoticed."""
    assert policy.AWAITING_THE_OWNER == {}
    waiting = offline_findings(locked(REPO)).awaiting
    assert sorted(one.split(" ", 1)[0] for one in waiting) == [
        "npm:argparse",
        "npm:caniuse-lite",
        "npm:lru-cache",
    ]
    assert set(BUILD_ONLY_AWAITING_THE_OWNER) == {
        ("npm", "argparse"),
        ("npm", "caniuse-lite"),
        ("npm", "lru-cache"),
    }
    shipped = {
        (c.name, c.licence) for c in locked(REPO) if c.ecosystem == "npm" and not c.build_only
    }
    pinned = {(key[1], one.licence) for key, one in BUILD_ONLY_AWAITING_THE_OWNER.items()}
    assert shipped.isdisjoint(pinned)


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


def test_every_console_dependency_is_read_and_its_licence_is_on_the_allowed_list() -> None:
    """**M27.15.79.** The console's lock is one of the locks the policy reads, every package it
    records is read with the licence it carries, and each of those passes the allowed list on
    its own, so no console package is let through by being judged beside another. Delete this and
    the console's lock can drop out of `NPM_LOCKS` with the CI step still green over the rest."""
    assert "console/package-lock.json" in NPM_LOCKS
    console = npm_locked((REPO / "console" / "package-lock.json").read_text(), "console")
    assert console and all(one.licence for one in console)
    assert {one.name for one in console} <= {one.name for one in locked(REPO)}
    assert offline_findings(console).refused == []


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
