"""The install's checks for the optional services it has switched on beside its profile.

`brain.ops.overlays` starts a service on a server when the install names it in
`INSTALL_SERVICES` and the server has room. That a container started proves nothing about the
leaf it is there for, so each service gets a check that asks the running service the question
the product relies on it to answer, from the worker the suite runs in, over the network the
service's compose file declares.

**A service the install has not switched on is not run, never failed.** An install that chose
not to run the detector, or whose server has no room for it, has not got it wrong, and a red
row there would teach an owner to ignore the page. The sentence says which of the two it is not
able to tell apart from here: the worker cannot see why a container is absent, only that the
setting does not name it.

**The detector is asked for every entity the scrub relies on it for, each with a probe that
carries one**, at the threshold `brain.ops.pii.PRESIDIO_BUILT_INS` sets for it, in the one
language it is configured for. Rejected: its health route, which answers as soon as the web
server listens and before the language model is loaded, and one probe for one entity, which is
the compose file's health check and proves the model loaded, not that the recognisers the scrub
needs are the ones running. A result names no data (`brain.ops.acceptance.A_RESULT_NAMES_NO_DATA`),
so a failure names the entity types missed, which are product words, and never a probe.

**The trace ledger is judged on what the server's docker said, because nothing else can say it.**
Whether a container is running, healthy and held to a memory limit is invisible from inside the
worker, which cannot read another container's ceiling. The deploy step asks docker once the
services are up and keeps the answer for the release (`brain.ops.overlays`,
`THE_SERVER_REPORTS_WHAT_RUNS_AND_THE_CHECK_READS_IT`), and these checks read only the report
for the release they are checking. Rejected: probing each service from the worker, which would
mean joining the worker to the ledger's network for a check, and would still say nothing about
limits; and accepting a report from an earlier release, which would judge containers that may
no longer exist.

Task ids: M32.2.1.1, M32.1.1.1, M32.1.1.2
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import structlog

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.ops.overlays import Seen

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 395

log = structlog.get_logger(__name__)

#: How long one analysis may take. The analyser runs spaCy's large English model over a sentence,
#: which is well under a second once loaded; twenty is for a server that is busy at deploy time.
ANALYSE_TIMEOUT_SECONDS: Final = 20.0

#: Said where the install runs no detector.
NO_DETECTOR_HERE: Final = (
    "this install runs no personal data detector: INSTALL_SERVICES does not name presidio and its "
    "profile does not deploy one"
)

#: Said where the detector answers and does not find one of the entities. Which ones it missed
#: goes to the worker's log as `acceptance.detector_asked`: they are product words, and a reason
#: is a literal sentence (`brain.ops.acceptance`).
THE_DETECTOR_MISSED_AN_ENTITY: Final = (
    "the personal data detector found no entity of a type the scrub relies on it for in a "
    "sentence carrying one, at the threshold set for it; the worker's log names the types"
)

#: Said where the detector is switched on and does not answer.
THE_DETECTOR_DID_NOT_ANSWER: Final = (
    "the personal data detector this install has switched on did not answer at its address from "
    "the worker"
)


@check(
    leaves=("M32.2.1.1",),
    sentence=(
        "The personal data detector this install has switched on is asked, from the worker, about "
        "a sentence carrying each entity the scrub relies on it for, in the one language it is "
        "configured for, and finds every one at or above the threshold set for it."
    ),
)
async def the_detector_finds_every_entity_the_scrub_relies_on_it_for(h: Harness) -> None:
    import httpx

    from brain.ops.overlays import components_switched_on, switched_on_here
    from brain.ops.pii import (
        PRESIDIO_BUILT_INS,
        PRESIDIO_LANGUAGE,
        PRESIDIO_PROBES,
        analyzer_address,
    )

    address = analyzer_address(
        h.settings.profile,
        h.settings.presidio_url,
        components_switched_on(switched_on_here()),
    )
    if address is None:
        raise CheckNotRunError(NO_DETECTOR_HERE)
    missed: list[str] = []
    async with httpx.AsyncClient(timeout=ANALYSE_TIMEOUT_SECONDS) as client:
        for wanted in PRESIDIO_BUILT_INS:
            try:
                answer = await client.post(
                    f"{address.rstrip('/')}/analyze",
                    json={
                        "text": PRESIDIO_PROBES[wanted.presidio_name],
                        "language": PRESIDIO_LANGUAGE,
                        "entities": [wanted.presidio_name],
                    },
                )
                answer.raise_for_status()
                found = answer.json()
            except (httpx.HTTPError, ValueError) as error:
                raise CheckFailedError(THE_DETECTOR_DID_NOT_ANSWER) from error
            if not any(
                isinstance(one, dict)
                and one.get("entity_type") == wanted.presidio_name
                and float(one.get("score", 0.0)) >= wanted.score_threshold
                for one in (found if isinstance(found, list) else [])
            ):
                missed.append(wanted.presidio_name)
    log.info("acceptance.detector_asked", asked=len(PRESIDIO_BUILT_INS), missed=sorted(missed))
    if missed:
        raise CheckFailedError(THE_DETECTOR_MISSED_AN_ENTITY)


# ------------------------------------------------------------------------ the trace ledger
#: Said where the install runs no trace ledger.
NO_LEDGER_HERE: Final = (
    "this install has not switched the trace ledger on: INSTALL_SERVICES does not name langfuse"
)

#: Said where the deploy step has not reported this release's services.
NOT_REPORTED_FOR_THIS_RELEASE: Final = (
    "the deploy step has not reported this release's optional services yet, so there is nothing "
    "the server said to judge; it reports them after every deploy that starts them"
)

#: Said where one of the ledger's services is absent, stopped or unhealthy.
A_LEDGER_SERVICE_IS_NOT_RUNNING: Final = (
    "one of the trace ledger's five services is not running and healthy on this release as the "
    "server reported it; the worker's log names which"
)

#: Said where one of them runs under a limit other than its budget, or none.
A_LEDGER_SERVICE_IS_NOT_HELD_TO_ITS_BUDGET: Final = (
    "one of the trace ledger's five services runs under a memory limit other than the one the "
    "product's budget gives it; the worker's log names which"
)


async def _ledger_as_reported(h: Harness) -> tuple[tuple[str, ...], dict[str, Seen]]:
    """The ledger's components and what the deploy step reported of them for this release.

    Not run, rather than failed, where the install has not switched the ledger on or the step has
    not reported this release: neither is the ledger being wrong.
    """
    from brain.ops.overlays import BY_NAME, OBSERVED_KEY, seen_in, switched_on_here
    from brain.ops.setting_store import read_namespace

    ledger = BY_NAME["langfuse"]
    if ledger not in switched_on_here():
        raise CheckNotRunError(NO_LEDGER_HERE)
    namespace = OBSERVED_KEY.split(".", 1)[0]
    async with h.sessions() as session:
        held = await read_namespace(session, namespace)
    row = held.get(OBSERVED_KEY)
    seen = None if row is None else seen_in(row.value, commit=h.settings.resolved_commit())
    if seen is None:
        raise CheckNotRunError(NOT_REPORTED_FOR_THIS_RELEASE)
    return ledger.components, dict(seen)


@check(
    leaves=("M32.1.1.1",),
    sentence=(
        "The trace ledger this install has switched on runs as its five services, web, worker, "
        "column store, cache and file store, each running and reported healthy by the server's "
        "own docker on this release, as the deploy step recorded it."
    ),
)
async def the_trace_ledger_runs_as_its_five_services(h: Harness) -> None:
    components, seen = await _ledger_as_reported(h)
    down = sorted(
        name
        for name in components
        if name not in seen or (seen[name].state, seen[name].health) != ("running", "healthy")
    )
    log.info("acceptance.ledger_services", asked=len(components), down=down)
    if down:
        raise CheckFailedError(A_LEDGER_SERVICE_IS_NOT_RUNNING)


@check(
    leaves=("M32.1.1.2",),
    sentence=(
        "Each of the trace ledger's five services runs under a memory limit equal to the one the "
        "product's budget gives it, as the server's own docker reported it on this release, so "
        "none can take memory the application needs."
    ),
)
async def every_trace_ledger_service_runs_under_its_budgeted_limit(h: Harness) -> None:
    from brain.ops.wiring import component

    components, seen = await _ledger_as_reported(h)
    off = sorted(
        name
        for name in components
        if name not in seen or seen[name].limit_mib != component(name).memory_mib
    )
    log.info("acceptance.ledger_limits", asked=len(components), off_budget=off)
    if off:
        raise CheckFailedError(A_LEDGER_SERVICE_IS_NOT_HELD_TO_ITS_BUDGET)
