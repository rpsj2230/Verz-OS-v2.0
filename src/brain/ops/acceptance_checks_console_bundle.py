"""The install acceptance check for the console's own fonts: the bundle this install serves names no
other host, and every font it ships is served as a font, with its licence notice beside it.

**It judges the bundle the install's own image carries, through the install's own server.** The
rule is `brain.ops.bundle_audit.audit`, the one CI runs over `console/dist` after the build, applied
here to `brain.console_static.CONSOLE_DIST`: the directory the running application answers from. A
font the build placed and the image dropped, or a stylesheet that names a hosted font service, is
found on the server it would harm and not on the runner that built it. Then every font the
stylesheets declare is asked for from the product's own fallback route on a throwaway application,
the way `the_console_is_served_as_an_installable_shell` asks for its icons, because "the bundle
carries a font" and "the install answers a request for it with a font" are two claims and only the
second is what a browser sees.

**What this does not claim, and the leaf's other half is not hidden by it.** The leaf also says
that loading any page makes no request to a font host. A request is made by a browser, so that half
is the browser harness's: `e2e/lib/checklist.ts` records every request each page makes, fonts
included, and fails on one that leaves the install and its identity provider. What this check proves
is the part that is true of the files: nothing a page loads names another host, so there is nothing
for a browser to be sent to. An image that carries no built console says so and the check is not
run.

Task ids: M27.15.75
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness
from brain.ops.bundle_audit import (
    A_FONT_HAS_NO_LICENCE_NOTICE_ID,
    A_REFERENCE_IS_A_FILE_THE_BUNDLE_CARRIES_ID,
    A_REFERENCE_NAMES_NO_OTHER_HOST_ID,
    A_SCRIPT_NAMES_NO_FONT_HOST_ID,
    THE_BUNDLE_CARRIES_NO_FONT_ID,
)

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2375

# ------------------------------------------------------------------ written-down reasons
#: Said when this image carries no built console to judge.
NO_CONSOLE_BUNDLE_IS_BUILT_HERE: Final = (
    "this image carries no built console bundle, so there are no fonts or stylesheets to read; the "
    "install's own image does"
)

#: What each kind of finding is said as. One literal sentence apiece, never the address it read.
THE_BUNDLE_NAMES_ANOTHER_HOST: Final = (
    "a page or stylesheet of the console names an address on another host"
)
THE_BUNDLE_NAMES_A_FILE_IT_LACKS: Final = (
    "a page or stylesheet of the console names a file the bundle does not carry"
)
A_SCRIPT_NAMES_A_FONT_HOST: Final = "a script of the console names a host that serves fonts"
A_FONT_HAS_NO_NOTICE: Final = "a font the console ships has no licence notice beside it"
THE_BUNDLE_SHIPS_NO_FONT: Final = "the console's stylesheets name no font file the bundle carries"
A_FONT_WAS_NOT_SERVED_AS_A_FONT: Final = "a font the console names was not served as a font"
A_FONT_MAY_NOT_BE_KEPT: Final = "a font the console names was served with no long lifetime"
THE_NOTICES_WERE_NOT_SERVED: Final = "the licence notice of the console's fonts was not served"


# ------------------------------------------------------------------ the check
@check(
    leaves=("M27.15.75",),
    sentence=(
        "The console this install serves names no address on another host in its page or its "
        "stylesheets, every font its stylesheets declare is served as a font that may be kept, and "
        "the licence notice of those fonts is served beside them."
    ),
)
async def the_console_names_no_font_host_and_serves_every_font_it_ships(h: Harness) -> None:
    del h
    import httpx
    from fastapi import FastAPI

    from brain.console_static import (
        CONSOLE_DIST,
        FONT_CONTENT_TYPES,
        bundle_entry,
        mount_console_fallback,
    )
    from brain.ops.bundle_audit import FONT_LICENCES_FILE, audit, fonts_in_use

    if bundle_entry() is None:
        raise CheckNotRunError(NO_CONSOLE_BUNDLE_IS_BUILT_HERE)
    # One literal sentence per kind of fault, in a fixed order, so a bundle with two says the first
    # and the next run says the other. The sentence never carries the address it read.
    found = {one.kind for one in audit(CONSOLE_DIST)}
    if A_REFERENCE_NAMES_NO_OTHER_HOST_ID in found:
        raise CheckFailedError(THE_BUNDLE_NAMES_ANOTHER_HOST)
    if A_REFERENCE_IS_A_FILE_THE_BUNDLE_CARRIES_ID in found:
        raise CheckFailedError(THE_BUNDLE_NAMES_A_FILE_IT_LACKS)
    if A_SCRIPT_NAMES_NO_FONT_HOST_ID in found:
        raise CheckFailedError(A_SCRIPT_NAMES_A_FONT_HOST)
    if THE_BUNDLE_CARRIES_NO_FONT_ID in found:
        raise CheckFailedError(THE_BUNDLE_SHIPS_NO_FONT)
    if A_FONT_HAS_NO_LICENCE_NOTICE_ID in found:
        raise CheckFailedError(A_FONT_HAS_NO_NOTICE)

    app = FastAPI()
    mount_console_fallback(app)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://acceptance.invalid") as c:
        for address in fonts_in_use(CONSOLE_DIST):
            served = await c.get(address)
            # The console answers every unknown address with its own page, so a font that is not
            # there is a 200 of HTML: a font is judged by being served as the type its file is.
            expected = FONT_CONTENT_TYPES.get(PurePosixPath(address).suffix.lower())
            # An extension the product names no type for has `expected` None, which nothing equals.
            if served.headers.get("content-type") != expected:
                raise CheckFailedError(A_FONT_WAS_NOT_SERVED_AS_A_FONT)
            if "immutable" not in served.headers.get("cache-control", ""):
                raise CheckFailedError(A_FONT_MAY_NOT_BE_KEPT)
        notices = await c.get(f"/{FONT_LICENCES_FILE}")
        if not notices.headers.get("content-type", "").startswith("text/plain"):
            raise CheckFailedError(THE_NOTICES_WERE_NOT_SERVED)
