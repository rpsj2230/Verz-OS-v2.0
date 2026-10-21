"""Install acceptance check: a desktop application is held to the browser's rules and given no way
out, and a desktop run has not been made on this host.

**Two halves, and only the first exists.** The first needs no host: the sandbox the product would
make for an allowlisted desktop application is built and held to its own gap check, each way a body
could be weakened (a route out, a proxy, a second network, a secret, another program, a writable
root, another runtime) is planted and refused, a window on another application's origin and a
command outside the applications directory are refused when declared, and the toolkit's widgets
are read as the browser's accessibility tree. It fails on a product defect on any install. The
second half would ask the install's launcher to make a desktop sandbox, read what the daemon made
of it and remove it, as `acceptance_checks_browser_sandbox` does for a browser. **That half is not
written because the launcher does not make desktop sandboxes yet and no desktop image is built**,
so this check always ends as not run, in a fixed sentence, and passing the first half is never
what closes the leaf (`A_DESKTOP_THAT_WAS_NEVER_STARTED_HAS_NOT_PASSED`).

A check that passed on the first half alone would close M19.8.1 on an install that has never
started a desktop, which is the claim the audit of 2026-09-17 exists to stop. Not run is the
answer that is true.

Task ids: M19.8.1
"""

from __future__ import annotations

from typing import Any, Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

#: Where this module's check stands on the Install page, after the declarations module's (2304).
CHECK_ORDER: Final = 2305

A_DESKTOP_THAT_WAS_NEVER_STARTED_HAS_NOT_PASSED: Final = (
    "No desktop has been started on this host: the launcher does not yet make desktop sandboxes "
    "and no desktop image is built, so what the product says a desktop run is has been checked "
    "and what a host did with one has not."
)

#: The application the check declares. Nothing runs it: it only has to be a name and a command the
#: declaration accepts.
APPLICATION: Final = "acceptance_notes"
COMMAND: Final = "/opt/desktop-apps/notes/notes"


@check(
    leaves=("M19.8.1",),
    sentence=(
        "A desktop application an administrator allowed runs in a gVisor container on a network "
        "with no gateway and no other member, with no proxy, no secret, nothing writable but "
        "memory and only the declared program, and only its own windows are addressable."
    ),
)
async def a_desktop_application_runs_in_a_sandbox_with_no_way_out(h: Harness) -> None:
    _the_product_describes_its_own_desktop_soundly(h.run)
    raise CheckNotRunError(A_DESKTOP_THAT_WAS_NEVER_STARTED_HAS_NOT_PASSED)


def _the_product_describes_its_own_desktop_soundly(run: str) -> None:
    """The half that needs no host: the bodies, the planted weaknesses and the declaration."""
    from dataclasses import replace

    from brain.browsing import desktop_app
    from brain.browsing.sessions import BROWSE_SURFACE
    from brain.browsing.targets import Surface, Verb
    from brain.browsing.wire import snapshot_from_accessibility

    origin = desktop_app.origin_of(APPLICATION)
    window = Surface(
        name="main",
        origin=origin,
        path="/main",
        verbs=frozenset({Verb.OPEN, Verb.READ}),
        capability=BROWSE_SURFACE,
        reads=("title",),
    )
    app = desktop_app.DesktopApp(name=APPLICATION, command=COMMAND, windows=(window,))
    first = desktop_app.desktop_sandbox_for(f"acc{run}a", app=app, app_image="app:check")
    second = desktop_app.desktop_sandbox_for(f"acc{run}b", app=app, app_image="app:check")
    for box in (first, second):
        if desktop_app.desktop_gaps(box, app):
            raise CheckFailedError("a desktop run's sandbox was built with a way out of it")
    if first.network_name == second.network_name or first.runner.name == second.runner.name:
        raise CheckFailedError("two desktop runs were given one network or one container name")
    for planted in _planted(first):
        if not desktop_app.desktop_gaps(planted, app):
            raise CheckFailedError("a desktop run's sandbox given a way out passed")
    if app.target().origins != frozenset({origin}):
        raise CheckFailedError("a desktop application was allowed an origin other than its own")
    elsewhere = replace(window, origin="https://elsewhere.example")
    for command, windows in (
        ("/bin/sh", (window,)),
        ("/opt/desktop-apps/../../bin/sh", (window,)),
        (COMMAND, (elsewhere,)),
        (COMMAND, ()),
    ):
        try:
            desktop_app.DesktopApp(name=APPLICATION, command=command, windows=windows)
        except desktop_app.DesktopError:
            continue
        raise CheckFailedError("a desktop application was declared that could reach another place")
    tree = desktop_app.accessibility_tree([(7, "push button", "Save"), (8, "unheard of", "")])
    nodes = snapshot_from_accessibility(tree, run_id="r", sequence=1, origin=origin).nodes
    if [(one.ref, one.role) for one in nodes] != [("n7", "button"), ("n8", "generic")]:
        raise CheckFailedError("a desktop's widgets were not read as the tree the enforcer reads")


def _planted(box: Any) -> tuple[Any, ...]:
    """Copies of a desktop sandbox with one way out planted in each."""
    from dataclasses import replace

    def runner_with(*, body: dict[str, Any] | None = None, **host: Any) -> Any:
        runner = box.runner
        planted = dict(runner.body if body is None else body)
        planted["HostConfig"] = {**runner.body["HostConfig"], **host}
        return replace(box, runner=replace(runner, body=planted))

    def with_env(extra: str) -> Any:
        return runner_with(body={**box.runner.body, "Env": [*box.runner.body["Env"], extra]})

    return (
        replace(box, network={**box.network, "Internal": False}),
        runner_with(body={**box.runner.body, "NetworkingConfig": {"EndpointsConfig": {"x": {}}}}),
        with_env("HTTPS_PROXY=http://egress:3128"),
        with_env("API_TOKEN=planted"),
        runner_with(
            body={**box.runner.body, "Cmd": ["/desktop_runner.py", "--command", "/bin/sh"]}
        ),
        runner_with(body={**box.runner.body, "Image": "app:check"}),
        runner_with(Binds=["/home/staff/.config:/home/desktop"]),
        runner_with(ReadonlyRootfs=False),
        runner_with(Runtime="runc"),
    )
