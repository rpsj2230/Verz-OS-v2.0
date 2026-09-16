"""Serving the built console from the application that answers its requests.

Until this module existed the console was built by nobody and served by nothing. `console/`
was compiled in CI to be type-checked and tested, its `dist/` was thrown away with the
runner, no compose file referenced it, and `src/brain/app.py` mounted no static files at
all. A finished install therefore answered on `/api/v1`, `/build` and `/health` and had no
administrative screen of any kind: `/` was the build tracker's landing page and `/first-run`
was a 404, which is the address the installer sends the first administrator to.

**One image, not two, and the argument is the origin rather than the megabytes.** The
alternative was a second container running nginx over the bundle, with the reverse proxy
sending `/api` to one and everything else to the other. Four things decide against it:

- *One origin is not a convenience here, it is the security design.* `console/src/auth/`
  runs authorisation code with PKCE and keeps the token in memory only, and
  `console/vite.config.ts` says in as many words that production serves the console from the
  same origin as the API so that `BRAIN_CORS_ORIGINS` stays empty. Splitting the two makes
  every console request cross-origin, which means a CORS allow list, `webOrigins` on the
  realm, and a preflight on every write. Two systems to change, neither of which fails
  loudly on its own.
- *The registered redirect URI is derived, not chosen.* `brain.setup_wizard` writes
  `INSTALL_OIDC_REDIRECT_URIS` as the web address the person typed plus
  `brain.setup_wizard.CALLBACK_PATH`, which is `/auth/callback`. The console's callback is
  therefore at the root of the web address by construction, and so are `/signed-out` and
  `/first-run`. A console served under a prefix would need that derivation changed, the
  realm re-imported, and `console/src/auth/constants.ts` to stop being true.
- *A second container is a second image to size for.* `brain.deployment.requirements`
  computes the disk a client needs as `len(images_in(files)) * IMAGE_GIB + DATA_GIB`, so a
  static server would add two gigabytes to every quoted requirement to serve four megabytes
  of JavaScript. It would also be a fourth thing the Cloudflare Tunnel option has to route,
  and `docker-compose.tunnel.yml` reaches exactly one service.
- *The install step count is the client's cost.* The console arriving inside the image the
  deploy already pulls is no step at all. A second service is one more thing that can be
  running an older bundle than the API it talks to, which is the failure that presents as
  "a screen that used to work".

What the single image costs is honest and small: the runtime layer carries the bundle, and
the build carries a Node stage that the Python layers do not (the stage is discarded). See
the Dockerfile, where the pinned Node major is the one `.github/workflows/ci.yml` already
runs the console's own checks on.

**The two halves are registered differently, and the difference is the whole design.**
`mount_console_entry` claims two exact paths and is called *before* every router, because
Starlette takes the first route that matches and `brain.docs_routes` also registers `/`.
`mount_console_fallback` claims nothing at all: it replaces `Router.default`, the handler
Starlette calls once the entire table has been tried. Neither enumerates a list of API
prefixes to avoid, because a list like that is a second copy of the routing table and it goes
stale on the day somebody adds a router.

A catch-all route was the obvious shape and is wrong, and the suite said so rather than a
reviewer. See `THE_FALLBACK_IS_REGISTERED_LAST_SO_IT_CANNOT_SHADOW_A_ROUTE` and the argument
on `mount_console_fallback`: registering last protects every path and no method at all.

**The bundle decides whether the console is served at all.** A checkout with no `dist/`
registers neither file route, so `/` is still the build landing page and every existing
behaviour is unchanged. That is what makes this safe to add: the image has a bundle, a
development tree usually does not, and the difference is a directory rather than a setting
somebody has to remember.

**Nothing about one installation is compiled into the bundle.** `console/src/config.ts` used
to read `VITE_KEYCLOAK_ISSUER` and `VITE_API_BASE_URL`, which Vite inlines as plain text at
build time, so a single image could only ever have been built for one client's identity
provider. The issuer and the client id now arrive at runtime from `brain.install`, through
the document this module serves, and the API base is `brain.api.API_PREFIX` because the two
share an origin. See `NO_INSTALLS_VALUES_ARE_BUILT_INTO_THE_BUNDLE`.

Task ids: M32.5.1.1, M32.5.1.2, M42.5.14
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from starlette.types import Receive, Scope, Send

from brain.api import API_PREFIX
from brain.docs_routes import COMING
from brain.install import InstallError, value_of

#: Where the built console lives, relative to the installed package.
#:
#: The same shape as `brain.docs_routes.DOCS`: `src/brain/console_static.py` has `/app` as its
#: third parent in the image and the repository root in a checkout, so one expression serves
#: both and the Dockerfile's `COPY` destination is the only thing that has to agree.
CONSOLE_DIST: Final = Path(__file__).resolve().parents[2] / "console" / "dist"

#: The bundle's entry document. Every console address renders this and nothing else.
INDEX_NAME: Final = "index.html"

#: Where the console reads its runtime configuration.
#:
#: Under `/api` rather than at the root for two reasons. It is the API answering, beside
#: `brain.docs_routes.status_json` at `/api/status.json`, which is the established place for a
#: document that is neither versioned nor gated. And `console/vite.config.ts` already proxies
#: `/api` to the application in development, so `npm run dev` reads the same document from the
#: same place as the deployed console with no second proxy rule to keep in step.
CONSOLE_CONFIG_PATH: Final = "/api/console.js"

#: The global the document assigns and `console/src/config.ts` reads.
CONSOLE_CONFIG_GLOBAL: Final = "__BRAIN_CONFIG__"

#: Why an install carrying a console answers the tracker's reserved addresses with the console.
A_RESERVED_ADDRESS_YIELDS_TO_THE_CONSOLE_THAT_REPLACED_IT: Final = (
    "brain.docs_routes answers /ask and /me with a page saying the screen is not built and "
    "promising the link will not move. Once the image carries a console, that page is a real "
    "route in front of the console's own: a click inside the console never asks the server, so "
    "nobody notices until they reload the page, and then the screen they were using says it "
    "does not exist. An install with no bundle keeps the reserved pages, because there the "
    "promise is still the truth."
)

#: The methods a browser asks a page for, and the only ones the fallback answers.
#:
#: HEAD is here because it is how a proxy, a monitor and a link checker ask whether an
#: address exists, and answering those with a 404 while GET works is a console that some
#: tools report as down. Starlette answers a HEAD against a GET route itself, so this set
#: has to name both.
_BROWSING_METHODS: Final = frozenset({"GET", "HEAD"})

#: The addresses FastAPI owns and this application switches off in production.
#:
#: They have no route there, so without this they would reach the console's fallback and
#: answer 200 with a page. An address the application deliberately turns off has to read as
#: absent, because the question a caller is asking at `/docs` is "is the interactive schema
#: published here", and a 200 answers it wrongly. `test_the_paths_the_console_declines_are_the
#: _ones_fastapi_serves_the_documentation_at` holds this set against what a development
#: application actually puts them at, so it is a fact read off the framework rather than three
#: strings somebody typed.
#:
#: This is the one set of paths the fallback knows about, and it is not the beginning of a list
#: of API prefixes: every route this application declares is already tried before the fallback
#: runs. These three are exactly the ones that exist in one environment and not the other.
DOCUMENTATION_PATHS: Final = frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"})

#: Why the console is served by this application rather than beside it.
THE_CONSOLE_AND_THE_API_SHARE_ONE_ORIGIN: Final = (
    "The console holds its token in memory and sends it to an API on its own origin, and the "
    "realm registers the redirect URI as the web address plus /auth/callback. Serving the "
    "bundle from a second host makes every request cross-origin, needs a CORS allow list here "
    "and webOrigins there, and moves the callback off the address the setup wizard derived."
)

#: Why the console's fallback is the router's default handler and never a catch-all route.
THE_FALLBACK_IS_REGISTERED_LAST_SO_IT_CANNOT_SHADOW_A_ROUTE: Final = (
    "A catch-all route is a full match for every GET, and Starlette prefers a full match to "
    "the partial one that would have answered 405, so a catch-all registered after every "
    "router still answers a GET on a POST-only path with the console's HTML and a 200. "
    "Measured: GET /api/v1/answer with the question in the query string went from refused to "
    "answered, which is the one thing that route declares no GET to prevent. Router.default "
    "runs only when the whole table has been tried, paths and methods both, so it can shadow "
    "neither. It also needs no list of API prefixes to skip, and such a list would be a "
    "second copy of the routing table that goes stale the day a router is added."
)

#: Why the issuer and the client id are served rather than compiled in.
NO_INSTALLS_VALUES_ARE_BUILT_INTO_THE_BUNDLE: Final = (
    "Vite inlines every VITE_-prefixed value into the JavaScript as plain text, so a bundle "
    "built against one company's issuer is a bundle that can only ever be installed at that "
    "company. One image installs everywhere or it is not a product. The values arrive at "
    "runtime from brain.install, which is the one reader of an installation's settings."
)


def bundle_entry(root: Path | None = None) -> Path | None:
    """The built `index.html`, or None when this tree carries no bundle.

    `root` is a parameter for the reason `brain.install.value_of` takes `env`: a path read
    through a module-level constant can be tested at exactly one value, and the case worth
    testing is the one where the directory is absent.
    """
    entry = (CONSOLE_DIST if root is None else root) / INDEX_NAME
    return entry if entry.is_file() else None


def file_in_bundle(path: str, root: Path | None = None) -> Path | None:
    """The bundle file a request names, or None when it names none.

    **The containment check is the point of this function and it is not decorative.** The
    request path arrives from the network and `Path` will follow `..` as far as it is asked
    to, so `/../../etc/passwd` resolves outside the bundle and `FileResponse` would serve it.
    Starlette normalises most of these away before routing, which is precisely why a guard
    here would look untested and unnecessary: it is the second of two, and the first one is
    somebody else's to change.

    Resolved on both sides before comparing, because a bundle reached through a symbolic link
    compares unequal to the same bundle reached directly, and on Windows a case difference
    does too.
    """
    base = (CONSOLE_DIST if root is None else root).resolve()
    if not base.is_dir():
        return None
    candidate = (base / path.lstrip("/")).resolve()
    if candidate == base or base not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def runtime_config(env: Mapping[str, str] | None = None) -> str:
    """The document that tells the console which installation it is serving.

    JavaScript rather than JSON, and that is the one decision here worth arguing. A JSON
    document has to be fetched, which makes configuration asynchronous, which means every
    module reading it becomes asynchronous or the application renders once with nothing
    configured and again with it. A blocking `<script>` in `index.html` is one request the
    browser already makes in parallel with the bundle, and `config.ts` stays a frozen object
    read at module load, which is what every one of its callers assumes.

    **A missing issuer is served as an empty string rather than as an error.**
    `INSTALL_OIDC_ISSUER` is required and `value_of` raises when it is unset, and raising here
    would give a blank page. The console collects configuration problems and renders them,
    naming the setting, to the person who deployed it, which is the same choice `brain.app`
    makes when it reports `sign_in` as unconfigured rather than refusing to start.
    """
    payload = {
        "apiBaseUrl": API_PREFIX,
        "issuer": _optional("INSTALL_OIDC_ISSUER", env),
        "clientId": _optional("INSTALL_OIDC_CLIENT_ID", env),
    }
    # `json.dumps` rather than an f-string, so a value containing a quote or a line break is
    # escaped by something that knows the grammar. These values come from an install's own
    # environment, which is not hostile, but a document assembled by concatenation is a
    # document that breaks on an apostrophe and nobody tests that case.
    return f"window.{CONSOLE_CONFIG_GLOBAL} = Object.freeze({json.dumps(payload)});\n"


def _optional(name: str, env: Mapping[str, str] | None) -> str:
    """A setting's value, or empty when this installation has not set a required one."""
    try:
        return value_of(name, env)
    except InstallError:
        return ""


def mount_console_entry(app: FastAPI) -> None:
    """The console's runtime configuration, and its entry document at the root.

    **Called before every `include_router`, and that is why `/` works.** `brain.docs_routes`
    registers `/` as the build tracker's landing page with a docstring saying "the product
    owns the root, until it exists, say so and point at what does". It exists now. Claiming
    the path here rather than editing that module means an image with no bundle keeps the
    landing page unchanged, and the build pages are reachable at `/build` either way, which
    is where every link on them already points.

    The configuration document is registered whether or not there is a bundle, because
    `npm run dev` proxies `/api` to an application running from a checkout, and a development
    console that cannot read its issuer is a development console that cannot sign anybody in.
    """

    @app.get(CONSOLE_CONFIG_PATH, include_in_schema=False)
    async def console_config() -> Response:
        # `no-store` rather than a long cache. This document names the identity provider, and
        # a browser holding a stale copy of it after an install moves its Keycloak signs
        # people in against a realm that no longer exists, with nothing on the screen saying
        # so. It is two hundred bytes beside a bundle of megabytes.
        return Response(
            content=runtime_config(),
            media_type="text/javascript",
            headers={"cache-control": "no-store"},
        )

    entry = bundle_entry()
    if entry is None:
        return

    @app.get("/", include_in_schema=False)
    async def console_root() -> Response:
        return _entry_response(entry)

    # Every address the build tracker reserved with a "not built yet" page, claimed for the same
    # reason as `/` and in the same place. `brain.docs_routes` registers each as a real route, so
    # the fallback below never sees a reload of `/ask` or `/me` and the person reloading their own
    # workspace was told it is not built. Read off `COMING` rather than listed, so an address
    # reserved there later yields to the console here without anybody remembering this file. See
    # `A_RESERVED_ADDRESS_YIELDS_TO_THE_CONSOLE_THAT_REPLACED_IT`.
    async def console_page() -> Response:
        return _entry_response(entry)

    for reserved in COMING:
        app.add_api_route(reserved, console_page, methods=["GET"], include_in_schema=False)


def mount_console_fallback(app: FastAPI) -> None:
    """Every other console address, and the bundle's own files.

    **This is the router's "nothing matched" handler, and it was a catch-all route until the
    suite showed why that cannot work.** `@app.get("/{path:path}")` registered last looks
    correct, and it is correct about paths: Starlette tries routes in order and every real one
    is tried first. It is wrong about *methods*. A route whose path matches and whose method
    does not is a `Match.PARTIAL`, and Starlette keeps looking for a full match before falling
    back to the partial one that would have answered 405. A catch-all is a full match for
    every GET, so it wins.

    Measured rather than reasoned about: `test_the_question_cannot_be_put_in_a_url` went from
    405 to 200 the moment the catch-all was added. That test exists because putting a question
    in a query string writes it to the proxy log, the browser history and a referer header,
    and `POST /api/v1/answer` declares no GET precisely so the router refuses one. With a
    catch-all, `GET /api/v1/answer?question=...` stopped being refused and started returning
    the console's HTML with a 200, which a caller reads as success. Every POST-only route in
    the application had the same hole.

    `Router.default` is called only after the whole table has been tried, full matches and
    partial ones both, so it cannot shadow a path or a method. It needs no list of API
    prefixes to avoid, which is the other half of the point: such a list is a second copy of
    the routing table and goes stale the day somebody adds a router. See
    `THE_FALLBACK_IS_REGISTERED_LAST_SO_IT_CANNOT_SHADOW_A_ROUTE`.

    **The interactive documentation's addresses are declined rather than answered.** In
    production `create_app` passes `docs_url=None` and `redoc_url=None`, so those paths have no
    route and would otherwise reach this handler and answer 200 with the console. A caller
    asking `/docs` is asking whether the schema is published here, and a page is the wrong
    answer to that question. See `DOCUMENTATION_PATHS`, which is held against what the
    framework actually serves them at rather than restated.

    **Only GET and HEAD are answered, and everything else keeps Starlette's own 404.** A POST
    to a path that does not exist is not a person following a link, and answering it with an
    HTML document would hide a client's mistake behind a 200. The handler that was there
    before this one is called for those, rather than a refusal written here, so a websocket or
    a future default keeps whatever behaviour it had.

    One handler rather than a `StaticFiles` mount beside it. The bundle has hashed files under
    `assets/` and unhashed ones at its root (`manifest.webmanifest`, `icon.svg`), and a mount
    for each is two registrations that have to stay in step with whatever Vite emits next.
    Asking "is this a file in the bundle" answers both, and answers `/agents` and `/first-run`
    with the entry document, which is what `createBrowserRouter` needs: the console's paths
    exist only in the browser, so a reload of one is a request this server has never heard of
    and must answer with the application rather than with a 404.
    """
    entry = bundle_entry()
    if entry is None:
        return

    # Kept rather than replaced, so anything this application does not serve as a console page
    # still fails the way the framework decided it should.
    unmatched = app.router.default

    async def console_or_unmatched(scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope["path"])
        if (
            scope["type"] != "http"
            or scope["method"] not in _BROWSING_METHODS
            or path in DOCUMENTATION_PATHS
        ):
            await unmatched(scope, receive, send)
            return
        found = file_in_bundle(path)
        response: Response = FileResponse(found) if found is not None else _entry_response(entry)
        await response(scope, receive, send)

    app.router.default = console_or_unmatched


def _entry_response(entry: Path) -> FileResponse:
    """The entry document, never cached.

    The file's name is `index.html` at every release, and its contents change on every one:
    it names the hashed bundle to load. A cached entry document is a browser loading last
    week's JavaScript from a file that is no longer there, which presents as a blank page
    after a deployment and clears itself only for whoever thinks to hard-reload. Everything
    under `assets/` carries a content hash in its name and may be cached for ever; this one
    file must not be.
    """
    return FileResponse(
        entry,
        media_type="text/html",
        headers={"cache-control": "no-store"},
    )
