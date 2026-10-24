"""Install acceptance check: a browser run's sandbox is what the product says it is, as the host's
own Docker daemon describes it, and none of it is left behind.

**Two halves, and the second is the one that proves anything.** The first half needs no container:
the sandbox the product would make for two runs is built and held to its own gap check, each way a
body could be weakened is planted and refused, and the comparison that reads the daemon's answer is
shown to find a changed runtime and a second network in a description made to the daemon's spelling.
It fails on a product defect on any install. The second half asks the install's own browser
launcher to make a sandbox for a rehearsal run, read what the daemon made of it, remove it and say
what is left (`brain.browsing.launcher.Launcher.rehearse`), and holds that answer to the same
expectations. Nothing is opened: no runner is started, so no page is fetched and nothing leaves the
host.

**It reports not run, with one sentence, when there is no host to ask.** A check that passed on the
first half alone would close the leaves it names on an install with no gVisor, no launcher and no
browser, which is the claim `docs/needs-rupash.md` and the audit of 2026-09-17 exist to stop. So a
switch that is off, a launcher that does not answer and a launcher that answers with nothing each
end the check as not run, in a fixed sentence (`A_CHECK_THAT_CANNOT_ASK_THE_HOST_HAS_NOT_PASSED`),
and only a daemon's description that matches closes it.

**The switch is read because the check starts containers.** The check at `CHECK_ORDER` 2301 calls
the driver and never starts anything. This one asks a service that holds the Docker socket to create
a network, a proxy and a runner on the host, briefly, and the owner has not agreed to that until
`browser_runs` is on.

Task ids: M19.1.1, M19.1.5, M19.1.6, M19.3.5, M19.6.4, M42.7.1
"""

from __future__ import annotations

import asyncio
from typing import Any, Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

#: Where this module's check stands on the Install page, after the browser module's (2301).
CHECK_ORDER: Final = 2302

#: How long the launcher is given to make, describe and remove one sandbox. Under the check's own
#: ceiling, so a daemon that hangs is this check's finding and not the run's timeout.
REHEARSAL_SECONDS: Final = 90.0

#: The one origin a rehearsal's proxy is built for. Nothing resolves it and nothing is sent to it:
#: no runner is started, so it only has to be an origin the sandbox accepts.
REHEARSAL_ORIGIN: Final = "https://acceptance-check.invalid"


A_CHECK_THAT_CANNOT_ASK_THE_HOST_HAS_NOT_PASSED: Final = (
    "A sandbox that was never made on this host proves nothing about this host. The first half "
    "of this check passes on any machine, so it can never be what closes a leaf: only the "
    "daemon's own description can, and where there is no daemon to ask the check says so and is "
    "not run."
)

SWITCH_OFF: Final = (
    "Browser runs are switched off on this install, so no sandbox was made and the launcher was "
    "not asked to make one."
)
LAUNCHER_ABSENT: Final = (
    "The browser launcher could not be reached from the worker, so no sandbox was made. It is "
    "present only where the browser overlay is composed on a host with gVisor."
)
LAUNCHER_SILENT: Final = (
    "The browser launcher accepted the connection and sent no answer in time, so what the host "
    "made of a sandbox was not read."
)


def _launcher_dial() -> Any:
    """Open the worker's one connection to the launcher. A seam, so a test can answer for it."""
    from brain.browsing.driver import dial_launcher

    return dial_launcher()


@check(
    leaves=("M19.1.1", "M19.1.5", "M19.1.6", "M19.3.5", "M19.6.4", "M42.7.1"),
    sentence=(
        "A browser run's sandbox is a gVisor container on a network of its own, with a proxy as "
        "the only member that can reach out, nothing writable but memory and its caps applied, as "
        "this host's Docker daemon describes it, none of it is left behind, and the launcher says "
        "whether the host offers KVM beside gVisor."
    ),
)
async def a_browser_sandbox_is_made_for_one_run_and_removed_with_it(h: Harness) -> None:
    from brain.browsing.driver import browser_runs_are_on
    from brain.browsing.wire import Kind, WireError, decode, encode

    _the_product_describes_its_own_sandbox_soundly(h.run)

    async with h.sessions() as session:
        switched_on = await browser_runs_are_on(session)
    if not switched_on:
        raise CheckNotRunError(SWITCH_OFF)

    from brain.browsing.sandbox import RUN_ID_RE

    run_id = f"rehearsal-{h.run}"[:63].lower().replace("_", "-")
    if not RUN_ID_RE.match(run_id):
        raise CheckFailedError("a rehearsal's run id could not be made into a container name")
    try:
        link = await _launcher_dial()
    except (OSError, TimeoutError):
        raise CheckNotRunError(LAUNCHER_ABSENT) from None
    try:
        await link.put_line(encode(Kind.REHEARSE, run_id=run_id, origins=[REHEARSAL_ORIGIN]))
        try:
            line = await asyncio.wait_for(link.next_line(), timeout=REHEARSAL_SECONDS)
        except TimeoutError:
            raise CheckNotRunError(LAUNCHER_SILENT) from None
    finally:
        await link.hang_up()
    if not line:
        raise CheckNotRunError(LAUNCHER_SILENT)
    try:
        answer = decode(line)
    except WireError:
        raise CheckFailedError(
            "the launcher answered a rehearsal with a line that is not one"
        ) from None
    if answer.kind is not Kind.REHEARSED or answer.fields["run_id"] != run_id:
        raise CheckFailedError("the launcher answered a rehearsal with something else")
    if answer.fields["gaps"]:
        raise CheckFailedError(
            "the host's daemon described the sandbox as weaker than the product says it is"
        )
    if answer.fields["runtime"] != "runsc":
        raise CheckFailedError("the host's daemon did not give the runner the gVisor runtime")
    if answer.fields["left_behind"] != 0:
        raise CheckFailedError("a rehearsal's sandbox was not wholly removed from the host")
    if answer.fields["virtualisation"] not in (
        "kvm_in_use",
        "kvm_available_not_used",
        "kvm_unavailable",
    ):
        raise CheckFailedError(
            "the launcher did not say whether this host offers KVM beside gVisor"
        )


def _the_product_describes_its_own_sandbox_soundly(run: str) -> None:
    """The half that needs no host: the bodies, the planted weaknesses and the comparison."""
    from dataclasses import replace

    from brain.browsing.inspection import (
        container_facts,
        faithful_description,
        network_facts,
        observed_gaps,
    )
    from brain.browsing.sandbox import EGRESS_NETWORK, RUNTIME, sandbox_for, sandbox_gaps
    from brain.ops.acceptance_checks_browser import _planted

    first = sandbox_for(f"acc{run}a", origins=frozenset({REHEARSAL_ORIGIN}), app_image="app:check")
    second = sandbox_for(f"acc{run}b", origins=frozenset({REHEARSAL_ORIGIN}), app_image="app:check")
    for box in (first, second):
        if sandbox_gaps(box):
            raise CheckFailedError("a run's sandbox was built with a way out of it")
        if box.runner.body["HostConfig"]["Runtime"] != RUNTIME:
            raise CheckFailedError("a run's runner was not given the gVisor runtime")
    if first.network_name == second.network_name or first.runner.name == second.runner.name:
        raise CheckFailedError("two runs were given one network or one container name")
    for planted in _planted(first):
        if not sandbox_gaps(planted):
            raise CheckFailedError(
                "a run's sandbox given a volume, a bind or a writable root passed"
            )
    routable = replace(first, network={**first.network, "Internal": False})
    if not sandbox_gaps(routable):
        raise CheckFailedError("a run's sandbox on a network with a gateway passed")

    def gaps_for(
        network: dict[str, Any], runner: dict[str, Any], egress: dict[str, Any]
    ) -> tuple[str, ...]:
        return observed_gaps(
            first.run_id,
            network=network_facts(network),
            runner=container_facts(runner),
            egress=container_facts(egress),
        )

    network, runner, egress = faithful_description(first)
    if gaps_for(network, runner, egress):
        raise CheckFailedError("the comparison reported a gap in a daemon that did as it was asked")
    other_runtime = {**runner, "HostConfig": {**runner["HostConfig"], "Runtime": "runc"}}
    if not gaps_for(network, other_runtime, egress):
        raise CheckFailedError("the comparison passed a runner given another runtime")
    _, on_two, _ = faithful_description(first, runner_networks=(first.network_name, EGRESS_NETWORK))
    if not gaps_for(network, on_two, egress):
        raise CheckFailedError("the comparison passed a runner given a second network")
