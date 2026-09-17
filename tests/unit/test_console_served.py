"""The console reaches a browser, and nothing it reaches shadows the API.

Every property here is one that fails silently. A console served at an address nobody can
reach looks exactly like a console nobody has opened yet; a fallback that swallows an API
path returns 200 and an HTML document, which a caller reads as success; and a client's
issuer compiled into the bundle is invisible until the second company installs the product
and signs in against the first one's identity provider.

The bundle is a fixture rather than a real build. Building the console takes a Node
toolchain and thirty seconds, and nothing asserted below is about what Vite emits: the
claims are about which request gets which file. What Vite emits is `console/tests`'s to
check, and that the image builds it at all is `test_the_image_builds_the_console` further
down.

Task ids: M32.5.1.1, M32.5.1.2, M42.5.14, M42.6.1
"""

from __future__ import annotations

import fnmatch
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from brain.api import API_PREFIX, NOT_FOUND
from brain.app import Settings, create_app
from brain.console_static import (
    CONSOLE_CONFIG_GLOBAL,
    CONSOLE_CONFIG_PATH,
    DOCUMENTATION_PATHS,
    INDEX_NAME,
    bundle_entry,
    file_in_bundle,
    runtime_config,
    served_accent,
    served_brand,
)
from brain.docs_routes import COMING
from brain.install import value_of
from brain.locale import Theme, accent_set
from tests.fixtures.http_client import Response

REPO = Path(__file__).resolve().parents[2]

#: What the fixture bundle's entry document says, so a response can be identified by it.
ENTRY_MARK = "<!doctype html><title>console entry</title><div id=root></div>"

#: An issuer and a client id no company owns, to prove a served value is read back.
A_DEPLOYMENTS_ISSUER = "https://idp.example.invalid/realms/brain"
A_DEPLOYMENTS_CLIENT = "brain-console-elsewhere"

#: An accent written in capitals, so the served fill proves it was read and normalised rather
#: than defaulted. A green nobody's brand guide is known to name.
A_DEPLOYMENTS_ACCENT = "#1F7A5C"


@pytest.fixture
def bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory shaped like a built console, pointed at by the module's own constant.

    Patched rather than passed, because `create_app` takes no path for this and should not:
    the bundle's location is a fact about the image's layout, and a setting for it is a
    setting somebody can point at a directory that is not a console.
    """
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / INDEX_NAME).write_text(ENTRY_MARK, encoding="utf-8", newline="\n")
    # `newline="\n"` on every one of these: without it Python rewrites the line endings to
    # CRLF on Windows, and a test comparing a served file with the text it wrote fails on one
    # developer's machine and passes on the runner.
    (dist / "assets" / "app-abc123.js").write_text(
        "export const x = 1;\n", encoding="utf-8", newline="\n"
    )
    (dist / "manifest.webmanifest").write_text('{"name":"c"}', encoding="utf-8")
    monkeypatch.setattr("brain.console_static.CONSOLE_DIST", dist)
    return dist


@pytest.fixture
def served(bundle: Path) -> Iterator[TestClient]:
    """The real application, built after the bundle exists, as a deployed image is."""
    app = create_app(Settings(env="development", database_url="", run_migrations=False))
    with TestClient(app) as client:
        yield client


@pytest.fixture
def unserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The application in a tree carrying no bundle, which is every checkout."""
    monkeypatch.setattr("brain.console_static.CONSOLE_DIST", tmp_path / "nothing")
    app = create_app(Settings(env="development", database_url="", run_migrations=False))
    with TestClient(app) as client:
        yield client


# ------------------------------------------------------------------ the console is reachable
def test_the_root_serves_the_console_entry_document(served: TestClient) -> None:
    """Delete this and `/` goes back to the build status page on an install that carries a
    console, which is what it did before this change and what makes the omission invisible:
    the address answers 200 either way."""
    got: Response = served.get("/")

    assert got.status_code == 200
    assert ENTRY_MARK in got.text
    assert got.headers["content-type"].startswith("text/html")


def test_a_console_sub_path_reloads_rather_than_404ing(served: TestClient) -> None:
    """`createBrowserRouter` puts `/agents`, `/records/invoice` and `/approvals/x` in the
    browser and nowhere else, so a reload of one is a path this server has never heard of.
    Without the fallback every deep link in the product is a 404 on refresh, and the two that
    matter most are not links a person typed: `/auth/callback` is where Keycloak returns a
    completed sign-in, and `/first-run` is where the installer sends the first administrator.

    Delete this and sign-in completes at the identity provider and lands on a missing page."""
    for path in ("/agents", "/records/invoice", "/approvals/s_1", "/auth/callback", "/deep/er"):
        got: Response = served.get(path)
        assert got.status_code == 200, path
        assert ENTRY_MARK in got.text, path


def test_an_address_the_tracker_reserved_reloads_as_the_console_once_there_is_one(
    served: TestClient,
) -> None:
    """`brain.docs_routes` reserves `/ask` and `/me` with a "not built yet" page and promises the
    link will not move. The console now serves both, and a route registered by that router is a
    real route, so the fallback never sees a reload of either: the person who bookmarked their
    workspace reloads it and is told it is not built.

    Delete this and every reserved address shadows the console page that replaced it, which is
    invisible from inside the console because a click inside it never asks the server."""
    for path in COMING:
        got: Response = served.get(path)
        assert got.status_code == 200, path
        assert ENTRY_MARK in got.text, path


def test_the_first_run_page_is_reachable(served: TestClient) -> None:
    """Named on its own rather than left inside the list above, because it is the one address
    an install cannot work without: `brain.deployment.installer` prints it, nobody has signed
    in yet, and there is no second way to reach the wizard. `console/src/setup/wizard.py`'s
    `FIRST_RUN_PATH` is read out of the console source rather than restated, so the path
    moving there fails here rather than shipping as a 404 on a fresh install.

    Delete this and the first thing a new client does is the thing that does not work."""
    path = _extracted(
        REPO / "console" / "src" / "setup" / "wizard.ts",
        r'^export const FIRST_RUN_PATH = "([^"]+)";$',
    )

    got: Response = served.get(path)

    assert got.status_code == 200
    assert ENTRY_MARK in got.text


def test_a_file_the_bundle_carries_is_served_as_itself(served: TestClient) -> None:
    """The positive case for the fallback's file branch. Without it every asset request
    answers with `index.html` and a 200, the browser parses HTML as JavaScript, and the
    console is a blank page with a console error nobody deployed to read.

    Delete this and a fallback that returns the entry document for everything passes every
    other test in this file."""
    asset: Response = served.get("/assets/app-abc123.js")
    manifest: Response = served.get("/manifest.webmanifest")

    assert asset.status_code == 200
    assert asset.text == "export const x = 1;\n"
    assert manifest.status_code == 200
    assert manifest.text == '{"name":"c"}'


def test_the_entry_document_is_never_cached(served: TestClient) -> None:
    """Its name never changes and its contents change on every release, because it names the
    hashed bundle to load. A cached copy is a browser asking for last week's JavaScript from
    a file the new image does not contain, which presents as a blank console after a
    successful deployment.

    Delete this and the first person to hit it is whoever deployed, and the fix they find is
    to tell everybody to hard-reload."""
    for path in ("/", "/agents"):
        got: Response = served.get(path)
        assert got.headers.get("cache-control") == "no-store", path


# --------------------------------------------------------------- nothing else is shadowed
def test_an_api_path_still_routes_when_the_console_is_served(served: TestClient) -> None:
    """The gate answers, rather than the console's HTML. A fallback that swallowed this would
    turn every refusal into a 200 carrying a page, and a caller parsing JSON would report it
    as a transport fault rather than as a route that is gone.

    Delete this and the console's fallback can be moved in front of the routers, which is the
    obvious place to put it and the one that breaks the API."""
    got: Response = served.get(f"{API_PREFIX}/me")

    assert got.status_code == 401
    assert ENTRY_MARK not in got.text
    assert got.headers["content-type"].startswith("application/json")


def test_a_get_on_a_post_only_api_path_is_still_refused(served: TestClient) -> None:
    """**This is the property a catch-all route cannot hold, and it is why the fallback is the
    router's default handler instead.** Starlette treats a path that matches with the wrong
    method as a partial match and keeps looking for a full one, so a catch-all wins and
    answers 200. `POST /api/v1/answer` declares no GET precisely so that a question cannot be
    put in a query string, where it lands in the proxy log, the browser history and a referer
    header.

    Delete this and the fallback goes back to a catch-all the day somebody finds
    `Router.default` obscure, and the question starts leaking again with every check green."""
    got: Response = served.get(
        f"{API_PREFIX}/answer", params={"question": "what is the price of WEB-1001"}
    )

    assert got.status_code == 405
    assert ENTRY_MARK not in got.text


def test_the_build_pages_and_health_are_untouched(served: TestClient) -> None:
    """The build tracker is how the owner reads progress and readiness is how the deployment
    decides whether to keep a container, and both are served by this same application at
    paths a fallback could have taken.

    Delete this and the console's arrival silently removes the pages nobody looks at until
    they need them, and readiness answering HTML is a deploy that never goes green."""
    build: Response = served.get("/build")
    live: Response = served.get("/health/live")

    assert build.status_code == 200
    assert ENTRY_MARK not in build.text
    assert "build status" in build.text
    assert live.status_code == 200
    assert live.json()["status"] == "ok"


def test_the_interactive_documentation_stays_absent_where_it_is_switched_off(
    bundle: Path,
) -> None:
    """In production `create_app` passes `docs_url=None`, so `/docs` and `/redoc` have no route
    at all and would fall to the console, which would answer 200 with a page. The question a
    caller asks at `/docs` is whether the schema is published here; a page answers it wrongly,
    and the two tests that hold the reading room closed assert a 404.

    **`bundle` is taken, and taking it is the whole test.** Without it `CONSOLE_DIST` points at
    a directory a checkout and a CI runner both lack, no console is served, and `/docs` answers
    404 for the reason it always did. The first version of this omitted the fixture and passed
    against a mutation that emptied `DOCUMENTATION_PATHS`, which is this repository's recurring
    failure: a guard checked in the one configuration where it cannot fire.

    Delete this and the console's arrival quietly turns two deliberate absences into pages, and
    the tests that would have caught it are in two other files whose subject is not the
    console."""
    app = create_app(Settings(env="production", database_url="", run_migrations=False))
    with TestClient(app) as client:
        for path in ("/docs", "/redoc"):
            got: Response = client.get(path)
            assert got.status_code == 404, path
            assert ENTRY_MARK not in got.text, path


def test_the_paths_the_console_declines_are_the_ones_fastapi_serves_documentation_at(
    bundle: Path,
) -> None:
    """The set is read off a development application rather than restated, because three
    strings typed into a constant are three strings that stop matching the day the framework
    or this application moves one, and the failure is a page where a 404 belongs.

    `bundle` is taken so the application under test is one that serves a console, which is the
    only configuration in which the set does anything.

    Delete this and `DOCUMENTATION_PATHS` becomes a comment about where the documentation used
    to be."""
    dev = create_app(Settings(env="development", database_url="", run_migrations=False))
    framework_owns = {
        dev.docs_url,
        dev.redoc_url,
        dev.swagger_ui_oauth2_redirect_url,
    } - {None}

    assert framework_owns == DOCUMENTATION_PATHS


def test_a_post_to_an_address_that_does_not_exist_is_not_a_page(served: TestClient) -> None:
    """A browser asks for a page with GET. A POST to a path nothing serves is a client
    mistake, and answering it with HTML and a 200 hides it.

    Delete this and the fallback starts answering every verb, which also means a mistyped
    write against this API looks like it worked."""
    got: Response = served.post("/nothing/here", json={})

    assert got.status_code == 404
    assert ENTRY_MARK not in got.text


def test_a_request_cannot_walk_out_of_the_bundle(served: TestClient, bundle: Path) -> None:
    """The path comes off the network and `Path` follows `..` wherever it is pointed. Starlette
    normalises most of these before routing, which is exactly what makes the check here look
    unnecessary: it is the second of two guards and the first is somebody else's to change.

    Delete this and the console's fallback becomes a file server for the image."""
    outside = bundle.parent / "secret.txt"
    outside.write_text("not for a browser", encoding="utf-8")

    assert file_in_bundle("../secret.txt", bundle) is None
    assert file_in_bundle("assets/../../secret.txt", bundle) is None
    got: Response = served.get("/../secret.txt")
    assert "not for a browser" not in got.text


def test_an_install_with_no_bundle_keeps_every_page_it_had(unserved: TestClient) -> None:
    """The console is served when the image carries one and not otherwise, so a checkout, a
    unit test and an image built without the console stage all behave exactly as they did.
    That is what makes this change safe to add rather than a change to every existing test.

    Delete this and the two halves can start registering unconditionally, which turns `/` into
    a 500 on a tree with no `dist` and breaks every developer's first request."""
    root: Response = unserved.get("/")
    missing: Response = unserved.get("/agents")

    assert root.status_code == 200
    assert "Task tracker" in root.text
    assert missing.status_code == 404


def test_the_bundle_is_found_by_its_entry_document_and_not_by_the_directory(
    tmp_path: Path,
) -> None:
    """An empty `console/dist`, which is what a failed or interrupted build leaves behind, is
    not a console. Testing the directory rather than the file would make such an image serve
    404s from a fallback that thinks it has a bundle, and the build pages would be gone too.

    Delete this and a half-finished build ships as a console that answers nothing."""
    (tmp_path / "dist").mkdir()

    assert bundle_entry(tmp_path / "dist") is None

    (tmp_path / "dist" / INDEX_NAME).write_text("x", encoding="utf-8")
    assert bundle_entry(tmp_path / "dist") is not None


# ------------------------------------------------------ nothing of one client is compiled in
def test_the_installs_identity_provider_is_served_rather_than_built_into_the_bundle(
    served: TestClient,
) -> None:
    """**The property that makes one image installable at every company.** Vite inlines a
    build-time value as plain text, so an issuer compiled in is an image only its own company
    can use, and nothing about the build would say so. Read back through the application
    rather than asserted on the function, so the route, the reader and the document shape are
    all exercised.

    Delete this and `config.ts` can go back to `import.meta.env` with every check green until
    the second company installs the product."""
    got: Response = served.get(CONSOLE_CONFIG_PATH)

    assert got.status_code == 200
    assert got.headers["content-type"].startswith("text/javascript")
    assert got.headers.get("cache-control") == "no-store"
    assert f"window.{CONSOLE_CONFIG_GLOBAL}" in got.text


def test_the_served_document_carries_this_installs_values_and_no_others() -> None:
    """The issuer, the client id and the API base, each from where it is decided: the first
    two from `brain.install`, which is the one reader of an installation's settings, and the
    base from the prefix the API actually mounts.

    Asserted on the parsed object rather than on the text, because the text is a JavaScript
    assignment and a substring check against it is satisfied by a comment.

    Delete this and a document that names the right fields with the wrong values passes, which
    is a console signing in against whatever the defaults happen to be."""
    env = {
        "INSTALL_OIDC_ISSUER": A_DEPLOYMENTS_ISSUER,
        "INSTALL_OIDC_CLIENT_ID": A_DEPLOYMENTS_CLIENT,
        "INSTALL_ACCENT_COLOUR": A_DEPLOYMENTS_ACCENT,
    }
    document = _parsed_config(runtime_config(env))

    assert document == {
        "apiBaseUrl": API_PREFIX,
        "issuer": A_DEPLOYMENTS_ISSUER,
        "clientId": A_DEPLOYMENTS_CLIENT,
        "accent": served_accent(env),
        "brand": served_brand(env),
    }


def test_the_served_accent_is_the_installs_colour_turned_into_what_the_console_draws() -> None:
    """The accent arrives as six colours rather than one, and every one of them is the value
    `brain.locale.accent_set` derived from what this install set, keyed the way
    `console/src/config.ts` reads them. The fill is the configured colour itself, normalised,
    because it is the company's and nothing about it is ours to change.

    The expected keys are spelled here rather than read from `served_accent`, because a test
    comparing the function's output with the function's output is green whatever the console
    is sent. `console/tests/accent.test.ts` holds the same six names from the other side.

    Delete this and the console can be sent the accent under names it does not read, and every
    new component draws in the neutral fallback on every install with nothing reporting it."""
    env = {"INSTALL_ACCENT_COLOUR": A_DEPLOYMENTS_ACCENT}
    derived = accent_set(A_DEPLOYMENTS_ACCENT)

    accent = _parsed_config(runtime_config(env))["accent"]

    assert accent == {
        "fill": "#1f7a5c",
        "onFill": derived.on_fill,
        "textLight": derived.text[Theme.LIGHT],
        "textDark": derived.text[Theme.DARK],
        "washLight": derived.wash[Theme.LIGHT],
        "washDark": derived.wash[Theme.DARK],
    }


def test_an_install_that_sets_no_accent_is_served_the_products_default_derived() -> None:
    """The positive sibling of the refusal below: an install that never set a colour still gets
    six measured colours, from the default `brain.install` declares, so a fresh install's
    components are drawn in something that reads rather than in nothing.

    Delete this and `served_accent` can return None for every install, which the console survives
    and which nobody would notice, because the fallback reads too."""
    accent = _parsed_config(runtime_config({}))["accent"]

    assert isinstance(accent, dict)
    assert accent["fill"] == accent_set(value_of("INSTALL_ACCENT_COLOUR", {})).fill


def test_an_accent_that_is_not_a_colour_is_served_as_none_and_the_console_still_starts() -> None:
    """A tint is not worth a stopped console. The value is somebody's typing on install day, and
    the console falls back to the design's own ink when it is sent none, so the right answer is
    none, with the issuer and the client id still served beside it.

    Delete this and a mistyped colour raises inside the document every page loads first, which is
    a blank page for everybody on the install."""
    env = {
        "INSTALL_OIDC_ISSUER": A_DEPLOYMENTS_ISSUER,
        "INSTALL_ACCENT_COLOUR": "brand orange",
    }

    document = _parsed_config(runtime_config(env))

    assert document["accent"] is None
    assert document["issuer"] == A_DEPLOYMENTS_ISSUER


def test_an_install_that_has_not_said_who_its_identity_provider_is_serves_an_empty_issuer() -> None:
    """`INSTALL_OIDC_ISSUER` is required and `brain.install.value_of` raises when it is unset,
    which is right everywhere else and would be a blank page here. The console collects the
    problem and renders it, naming the setting, to whoever deployed it. That is the same
    choice `brain.app` makes in reporting `sign_in` unconfigured rather than refusing to
    start, and it matters on exactly one install: the one that has not run the wizard yet, and
    whose first administrator reaches the wizard through this console.

    Delete this and a fresh install's console is a blank page, and the wizard that would have
    set the issuer is behind it."""
    document = _parsed_config(runtime_config({}))

    assert document["issuer"] == ""
    # The client id still has one, because the realm this product ships defines it and a
    # console with no client id at all cannot even build an authorisation request.
    assert document["clientId"] == "brain-console"


def test_no_source_file_in_the_console_reads_a_build_time_setting() -> None:
    """The Python-side sibling of `console/tests/config.test.tsx`'s first check, here because
    this is the suite that gates a deploy and the console's own is a separate job.

    Asserted over every source file rather than over `config.ts`, because the next file to do
    it will be a different one, and on the read itself rather than on the variable's name,
    because a value named anything at all is inlined the same way.

    Delete this and the bundle quietly becomes one client's again."""
    offenders = [
        path.relative_to(REPO).as_posix()
        for path in (REPO / "console" / "src").rglob("*.ts*")
        if "import.meta.env" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


# --------------------------------------------------------------------- the image builds it
def test_the_image_builds_the_console_and_carries_the_bundle() -> None:
    """A console the image does not build is a console that does not exist, and the failure is
    silent in the worst way: every test in this file passes against a fixture directory, and
    the deployed application simply serves the build pages instead.

    Asserted on the parsed stages rather than on a substring of the file, because a comment
    naming `npm ci` would satisfy a text search. Four claims, and each one alone is satisfied
    by a broken build: a Node stage exists, it installs from the lockfile, it runs the build,
    and the runtime stage copies what that produced.

    Delete this and the console stage can be dropped from the Dockerfile to make the build
    faster, which it would."""
    stages = _dockerfile_stages()

    assert "console" in stages, "the Dockerfile has no stage that builds the console"
    console = stages["console"]
    assert console.base.startswith("node:"), f"the console is built on {console.base}"
    assert any(line.startswith("RUN npm ci") for line in console.run), (
        "the console stage does not install from the lockfile"
    )
    assert any("npm run build" in line for line in console.run), (
        "the console stage never builds the bundle"
    )

    copied = [
        line
        for line in stages["runtime"].copy
        if line.startswith("--from=console") and line.endswith("/app/console/dist")
    ]
    assert len(copied) == 1, f"the runtime stage copies the bundle {len(copied)} times"


def test_the_node_the_image_builds_with_is_the_node_ci_checks_with() -> None:
    """A bundle built by a toolchain no check ever runs is a bundle whose first exercise is a
    client's browser. CI type-checks, lints, tests and builds the console on one Node major;
    this holds the image to the same one rather than to a number written twice.

    Read out of the workflow rather than restated, so the pair moves together when somebody
    upgrades. Delete this and the two drift, and the difference shows up as a build that works
    in CI and produces different output in the image.

    Delete this and nothing notices the day the Dockerfile is pinned to a Node that CI has
    never run."""
    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text("utf-8"))
    console_job = next(
        job for job in workflow["jobs"].values() if "console" in str(job.get("name", "")).lower()
    )
    checked_with = {
        str(step["with"]["node-version"])
        for step in console_job["steps"]
        if "node-version" in step.get("with", {})
    }

    built_with = _dockerfile_stages()["console"].base
    major = built_with.removeprefix("node:").split("-")[0].split(".")[0]

    assert checked_with == {major}, (
        f"the image builds the console on node {major} and CI checks it on {checked_with}"
    )


def test_the_build_context_carries_what_the_console_stage_needs() -> None:
    """**The middle of the chain, and the half that has already gone wrong here once.** That
    the Dockerfile copies the console and the runtime stage takes its `dist` proves the two
    ends agree and says nothing about whether the build can see the files at all: `ops` was
    excluded by `.dockerignore` and the realm's COPY failed on the build machine with "not
    found" while every test passed. Docker is not installed on the development laptop, so this
    is the only thing between that mistake and CI.

    `node_modules` is excluded on purpose and is checked as such, because it is the one
    exclusion whose removal is invisible: the build would still work and would carry hundreds
    of megabytes of a host's platform-specific modules into the context of every image.

    Delete this and somebody tidies `.dockerignore` and the console stage stops building."""
    rules = [
        line.strip()
        for line in (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    for wanted in (
        "console/package.json",
        "console/package-lock.json",
        "console/index.html",
        "console/src/config.ts",
        "console/scripts/export-openapi.py",
    ):
        assert not _excluded(wanted, rules), (
            f".dockerignore excludes {wanted}, so the console stage fails on the build machine "
            "with a message about a missing file while every check here still passes"
        )

    assert _excluded("console/node_modules", rules), (
        "the host's node_modules is no longer excluded from the build context"
    )


def test_the_console_adds_no_image_to_the_stack_a_client_has_to_size_for() -> None:
    """The other half of the one-image argument, held rather than merely written down.
    `brain.deployment.requirements` sizes a client's disk as two gigabytes per image plus the
    data, so a second container serving four megabytes of JavaScript would add two gigabytes
    to every quoted requirement, appear in the install guide's service table, and need a route
    of its own through the Cloudflare Tunnel.

    Delete this and somebody adds an nginx service to `docker-compose.yml` because it is the
    conventional shape, and the sizing, the guide and the tunnel all quietly become wrong."""
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    images = {str(service.get("image", "")) for service in compose["services"].values()}

    assert not any("nginx" in image or "caddy" in image for image in images), (
        "a static web server joined the standard stack; the console is served by the "
        "application from inside its own image"
    )
    assert compose["services"]["app"]["image"].startswith("${APP_IMAGE:?")


@dataclass(frozen=True)
class Stage:
    """One build stage of the Dockerfile: what it starts from, and what it runs and copies."""

    base: str
    run: list[str]
    copy: list[str]


def _dockerfile_stages() -> dict[str, Stage]:
    """The Dockerfile as stages, each with its base image and its RUN and COPY lines.

    Parsed rather than searched. A test asserting `"npm ci" in dockerfile` is satisfied by
    this repository's own comments, which is a failure mode CLAUDE.md records twice.
    Continuation lines are joined, so a RUN split over three lines is one line here.
    """
    text = (REPO / "Dockerfile").read_text(encoding="utf-8")
    joined = re.sub(r"\\\r?\n\s*", " ", text)
    stages: dict[str, Stage] = {}
    current: Stage | None = None
    for raw in joined.splitlines():
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        from_stage = re.match(r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?$", line, re.I)
        if from_stage is not None:
            current = Stage(base=from_stage.group(1), run=[], copy=[])
            stages[from_stage.group(2) or from_stage.group(1)] = current
            continue
        if current is None:
            continue
        if line.startswith("RUN"):
            current.run.append(line)
        elif line.startswith("COPY"):
            current.copy.append(line.removeprefix("COPY").strip())
    return stages


def _excluded(wanted: str, rules: list[str]) -> bool:
    """Whether `.dockerignore` keeps a path out of the build context.

    Docker applies every rule in order and the last one that matches wins, with `!` negating,
    and a rule matching a parent directory excludes everything under it. Both are reproduced
    here rather than approximated with a substring search, which would call `console/dist`
    excluded when the rule said `!console/dist`.
    """
    excluded = False
    parts = wanted.split("/")
    prefixes = ["/".join(parts[: n + 1]) for n in range(len(parts))]
    for rule in rules:
        negated = rule.startswith("!")
        pattern = rule.removeprefix("!")
        if any(fnmatch.fnmatch(one, pattern) for one in prefixes):
            excluded = not negated
    return excluded


def _parsed_config(document: str) -> dict[str, object]:
    """The object out of the served JavaScript, parsed as JSON rather than matched on.

    The document is one assignment of a frozen object literal, so the JSON is exactly the text
    between the outermost braces. Asserting on that object is asserting on structure; asserting
    on the text would pass for a document that names the right fields inside a comment.
    """
    found = re.search(r"Object\.freeze\((\{.*\})\);", document, re.S)
    assert found is not None, f"the served document is not one frozen object: {document!r}"
    parsed: dict[str, object] = json.loads(found.group(1))
    return parsed


def _extracted(path: Path, pattern: str) -> str:
    """One value out of a source file, failing loudly when the shape has moved.

    A missing match returning empty would make the caller's assertion vacuous, which is the
    bug this helper exists to avoid.
    """
    found = re.search(pattern, path.read_text(encoding="utf-8"), re.M)
    assert found is not None, f"{pattern} no longer matches anything in {path.name}"
    return found.group(1)


def test_an_api_address_nothing_serves_is_a_refusal_in_words_and_not_the_console(
    served: TestClient,
) -> None:
    """A GET under the API's prefix that no route serves answers 404 with a sentence and a
    reference, and a console address beside it still reloads as the console.

    Delete this and a console one release ahead of its server is answered with the entry document
    and a 200, which it reads as a success with no body, so the screen draws nothing and says
    nothing. See `brain.console_static.AN_API_ADDRESS_NOTHING_SERVES_IS_NOT_A_PAGE`."""
    missing: Response = served.get(f"{API_PREFIX}/a-screen-this-server-does-not-have")
    page: Response = served.get("/a-screen-this-server-does-not-have")

    assert missing.status_code == 404
    assert ENTRY_MARK not in missing.text
    assert missing.json()["message"] == NOT_FOUND
    assert missing.json()["trace_id"] == missing.headers["x-trace-id"]
    assert page.status_code == 200
    assert ENTRY_MARK in page.text


def test_the_served_brand_is_the_names_and_logo_this_install_set() -> None:
    """**Branding is configuration only if something draws it.** The console's header read
    "Company Brain" as a literal until 2026-09-17, so a company name saved by the wizard reached
    the API schema's title and no screen a person looks at.

    Asserted against values a fictitious company set, and against the declared defaults when it
    set none, so a function returning the defaults for every install fails.

    Delete this and the header can go back to a literal while the setting still saves."""
    from brain.install import BY_NAME

    env = {
        "INSTALL_COMPANY_NAME": "Northwind Trading",
        "INSTALL_PRODUCT_NAME": "Knowledge Desk",
        "INSTALL_LOGO_URL": "https://assets.northwind.example/logo.svg",
    }

    assert _parsed_config(runtime_config(env))["brand"] == {
        "companyName": "Northwind Trading",
        "productName": "Knowledge Desk",
        "logoUrl": "https://assets.northwind.example/logo.svg",
    }
    assert served_brand({}) == {
        "companyName": BY_NAME["INSTALL_COMPANY_NAME"].default,
        "productName": BY_NAME["INSTALL_PRODUCT_NAME"].default,
        "logoUrl": BY_NAME["INSTALL_LOGO_URL"].default,
    }
