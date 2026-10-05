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

Task ids: M32.2.1.1
"""

from __future__ import annotations

from typing import Final

import structlog

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

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
