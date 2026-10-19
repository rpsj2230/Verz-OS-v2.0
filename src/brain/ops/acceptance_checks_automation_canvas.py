"""The install's checks for the automation canvas as it runs: three containers held to their
budgets, no way out but the allowlisted proxy and no credential of the application's, and a switch
that is the setting and nothing else.

`brain.ops.acceptance_checks_automation` proves the door the canvas's piece calls. These prove the
other half of M32.6.1, the container that calls it, and they cannot be proved from inside the
application: which networks a container sits on, which variables it was created with and what its
proxy was started to allow are known to the server's docker alone. So, as
`brain.ops.acceptance_checks_services` does for the trace ledger, they judge what the deploy step
reported for this release: `brain.ops.overlays` (running, health, limits) and
`brain.ops.automation_report` (networks, variable names, routes, the proxy's allowlist and its
answer to a host on no list).

**An install that has not switched the canvas on is not run, never failed.** The canvas is optional
and ships off. A red row on an install that chose not to run it would teach its owner to ignore the
page. The third check is the one that speaks for that install: it is judged in both directions.

**The third check is the leaf's own claim, "enabled by configuration and not a fork".** The one
setting is `INSTALL_SERVICES`. Where it names `automation` the canvas runs, from the one image's own
compose file; where it does not, no canvas container is in the step's report for this release. A
fork would be a canvas that runs when the setting says it does not, or one the setting names that
never starts, and both are findings. Rejected: reading `brain.ops.automation.enabled_for`, which
asks a configuration key named `activepieces` that nothing sets (the install's own switch has been
`INSTALL_SERVICES` since the canvas became an overlay), so a check on it would prove a switch nobody
turns.

**A reason is one literal sentence.** Which name or which gap is in the worker's log
(`acceptance.canvas_gaps`), as the ledger's checks do for theirs: a name of a variable is not a
secret, and a reason is served on a page.

Task ids: M32.6.1.1, M32.6.1.2, M32.6.1.4
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import structlog

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.ops.automation_report import CanvasFacts
    from brain.ops.overlays import Seen

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 212

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons
#: Said where the install has not switched the canvas on.
NO_CANVAS_HERE: Final = (
    "this install has not switched the automation canvas on: INSTALL_SERVICES does not name "
    "automation"
)

#: Said where the deploy step has not reported this release's optional services.
THE_SERVICES_ARE_NOT_REPORTED: Final = (
    "the deploy step has not reported this release's optional services yet, so there is nothing "
    "the server said to judge; it reports them after every deploy that starts them"
)

#: Said where the deploy step has not reported what it saw of the canvas for this release.
THE_CANVAS_FACTS_ARE_NOT_REPORTED: Final = (
    "the deploy step has not reported what it saw of the automation canvas for this release yet; "
    "it reports it after every deploy that starts the canvas"
)

A_CANVAS_SERVICE_IS_NOT_RUNNING: Final = (
    "one of the automation canvas's three services, the editor, its egress proxy or its database, "
    "is not running and healthy on this release as the server reported it; the worker's log says "
    "which"
)

A_CANVAS_SERVICE_IS_NOT_HELD_TO_ITS_BUDGET: Final = (
    "one of the automation canvas's three services runs under a memory limit other than the one "
    "the product's budget gives it, so it can take memory the application needs; the worker's log "
    "says which"
)

THE_CANVAS_HOLDS_A_CREDENTIAL_IT_WAS_NOT_GIVEN: Final = (
    "the running automation canvas holds a credential that is not its own: a variable that "
    "carries a secret beside its own three, one named as the application's are, or a connection "
    "string; the worker's log names the variables"
)

THE_CANVAS_IS_ON_A_NETWORK_THAT_IS_NOT_ITS_OWN: Final = (
    "the running automation canvas or its proxy sits on a network other than the ones its file "
    "gives it, so it may be able to reach what those networks do not"
)

THE_CANVAS_HAS_A_WAY_OUT_THAT_IS_NOT_ITS_PROXY: Final = (
    "the running automation canvas has a default route, so it has a way out that is not its "
    "allowlisted proxy"
)

THE_CANVAS_ROUTES_WERE_NOT_READ: Final = (
    "the step could not read the running automation canvas's routes, and a route nobody read is "
    "not a route that is absent"
)

THE_PROXY_RUNS_ANOTHER_ALLOWLIST: Final = (
    "the running egress proxy was started with a list of hosts that is not the product's "
    "allowlist, exactly, as the server's docker reported it"
)

THE_PROXY_DID_NOT_REFUSE_AN_UNLISTED_HOST: Final = (
    "the running egress proxy did not refuse, when asked from its own address, to open a tunnel "
    "to a host that is on no list"
)

THE_CANVAS_IS_NAMED_AND_NOT_RUNNING: Final = (
    "INSTALL_SERVICES names automation and the deploy step did not report all three of its "
    "services running on this release"
)

THE_CANVAS_RUNS_AND_IS_NOT_NAMED: Final = (
    "INSTALL_SERVICES does not name automation and the deploy step reported one of its services "
    "running on this release"
)


# ------------------------------------------------------------------------ the helpers
async def _stored(h: Harness, key: str) -> object | None:
    """The value kept under `key` in the `overlay` namespace, or None where nothing is kept."""
    from brain.ops.setting_store import read_namespace

    async with h.sessions() as session:
        held = await read_namespace(session, key.split(".", 1)[0])
    row = held.get(key)
    return None if row is None else row.value


async def _services_reported(h: Harness) -> dict[str, Seen]:
    """What the step said of this release's optional services, or not run where it said nothing."""
    from brain.ops.overlays import OBSERVED_KEY, seen_in

    seen = seen_in(await _stored(h, OBSERVED_KEY), commit=h.settings.resolved_commit())
    if seen is None:
        raise CheckNotRunError(THE_SERVICES_ARE_NOT_REPORTED)
    return dict(seen)


def _switched_on() -> bool:
    from brain.ops.overlays import BY_NAME, switched_on_here

    return BY_NAME["automation"] in switched_on_here()


def _components() -> tuple[str, ...]:
    from brain.ops.overlays import BY_NAME

    return BY_NAME["automation"].components


# -------------------------------------------------------------------------------- M32.6.1.1
@check(
    leaves=("M32.6.1.1",),
    sentence=(
        "The automation canvas this install has switched on runs as its three services, the "
        "editor, its egress proxy and its own database, each running and reported healthy by the "
        "server's own docker on this release and held to the memory limit the product's budget "
        "gives it, as the deploy step recorded it."
    ),
)
async def the_canvas_runs_as_three_services_each_held_to_its_budget(h: Harness) -> None:
    from brain.ops.wiring import component

    if not _switched_on():
        raise CheckNotRunError(NO_CANVAS_HERE)
    seen = await _services_reported(h)
    names = _components()
    down = sorted(
        name
        for name in names
        if name not in seen or (seen[name].state, seen[name].health) != ("running", "healthy")
    )
    log.info("acceptance.canvas_services", asked=len(names), down=down)
    if down:
        raise CheckFailedError(A_CANVAS_SERVICE_IS_NOT_RUNNING)
    off = sorted(name for name in names if seen[name].limit_mib != component(name).memory_mib)
    log.info("acceptance.canvas_limits", off=off)
    if off:
        raise CheckFailedError(A_CANVAS_SERVICE_IS_NOT_HELD_TO_ITS_BUDGET)


# -------------------------------------------------------------------------------- M32.6.1.2
async def _facts(h: Harness) -> CanvasFacts:
    from brain.ops.automation_report import FACTS_KEY, facts_in

    found = facts_in(await _stored(h, FACTS_KEY), commit=h.settings.resolved_commit())
    if found is None:
        raise CheckNotRunError(THE_CANVAS_FACTS_ARE_NOT_REPORTED)
    return found


@check(
    leaves=("M32.6.1.2",),
    sentence=(
        "The automation canvas this install runs sits on its own internal network and the tool "
        "network and no other, has no default route, holds no variable that carries a credential "
        "beyond its own three and no connection string, and its egress proxy runs exactly the "
        "product's allowlist and refuses a host on no list, as the deploy step saw on this release."
    ),
)
async def the_canvas_has_no_way_out_but_its_proxy_and_no_foreign_secret(h: Harness) -> None:
    from brain.ops.automation_report import Gap, foreign_credential_names, gaps

    if not _switched_on():
        raise CheckNotRunError(NO_CANVAS_HERE)
    facts = await _facts(h)
    found = gaps(facts)
    log.info(
        "acceptance.canvas_gaps",
        gaps=[one.value for one in found],
        variables=list(foreign_credential_names(facts)),
    )
    # One sentence for each kind of fault, written out so each is a literal constant at its raise
    # (`brain.ops.acceptance`: a reason names no data), and in the order that matters most.
    kinds = set(found)
    if kinds & {Gap.FOREIGN_CREDENTIAL, Gap.CONNECTION_STRING, Gap.APPLICATION_VARIABLE}:
        raise CheckFailedError(THE_CANVAS_HOLDS_A_CREDENTIAL_IT_WAS_NOT_GIVEN)
    if kinds & {Gap.CANVAS_NETWORKS, Gap.PROXY_NETWORKS}:
        raise CheckFailedError(THE_CANVAS_IS_ON_A_NETWORK_THAT_IS_NOT_ITS_OWN)
    if Gap.DEFAULT_ROUTE in kinds:
        raise CheckFailedError(THE_CANVAS_HAS_A_WAY_OUT_THAT_IS_NOT_ITS_PROXY)
    if Gap.ROUTES_UNKNOWN in kinds:
        raise CheckFailedError(THE_CANVAS_ROUTES_WERE_NOT_READ)
    if Gap.ALLOWLIST in kinds:
        raise CheckFailedError(THE_PROXY_RUNS_ANOTHER_ALLOWLIST)
    if Gap.NOT_REFUSED in kinds:
        raise CheckFailedError(THE_PROXY_DID_NOT_REFUSE_AN_UNLISTED_HOST)


# -------------------------------------------------------------------------------- M32.6.1.4
@check(
    leaves=("M32.6.1.4",),
    sentence=(
        "The automation canvas runs on this install exactly where INSTALL_SERVICES names it: where "
        "it does, all three of its services run on this release; where it does not, none of them "
        "is in the deploy step's report for this release. The one setting is the whole switch."
    ),
)
async def the_canvas_runs_where_the_setting_names_it_and_nowhere_else(h: Harness) -> None:
    seen = await _services_reported(h)
    names = _components()
    present = sorted(name for name in names if name in seen)
    log.info("acceptance.canvas_switch", named=_switched_on(), present=present)
    if _switched_on():
        if any(name not in seen or seen[name].state != "running" for name in names):
            raise CheckFailedError(THE_CANVAS_IS_NAMED_AND_NOT_RUNNING)
    elif present:
        raise CheckFailedError(THE_CANVAS_RUNS_AND_IS_NOT_NAMED)
