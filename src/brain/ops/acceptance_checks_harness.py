"""Install checks for the agent runtime's own rules: one place gives a model tools, and an author's
test never blocks a publish.

Both rules are written as tests in the repository. A test in the repository says the source was
right when it was committed, and what an install runs is the source it was built from, so the
sentences are asked again here, of the code actually deployed and its own publish gate.

**One runtime (M13.7.1).** `brain.ops.runtime_scan.findings` reads every module of the deployed
`brain` package and reports a second place that calls a model while holding a tool catalogue.
The same function is what the repository's unit test calls, so the two cannot disagree about
which modules are allowed. The check also reads a probe: a module written in the check that
holds a catalogue and calls a model is added to what the scan reads, and the scan must name it.
That shows the scan can say no, which a clean answer alone cannot. An install built without its
Python source reads nothing, and says so as not run rather than passing over an empty directory.

**An author's test is advisory for ever (M20.4.2).** The publish gate is asked, through
`brain.builder.publish.decide`, with a check an author wrote that failed and with one the system
wrote that failed. The first leaves the publish allowed and the second stops it, and a check the
author wrote has no field that could raise it. Rejected: driving the route with a draft whose
golden set fails, because the author's questions are not run at publish until a model answers for
an agent (`brain.builder.agent_drafts.system_check` says so), so the route would pass for a
reason that is not this rule.

Task ids: M13.7.1, M20.4.2
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 850

NO_SOURCE_HERE: Final = (
    "This install carries the product without its Python source, so there is nothing to read for "
    "a second place that gives a model tools."
)
A_SECOND_RUNTIME_EXISTS: Final = (
    "the product's source holds a second place that calls a model while holding tools"
)
THE_SCAN_CANNOT_SAY_NO: Final = (
    "the scan did not name a module written to call a model while holding a tool catalogue"
)
AN_AUTHOR_S_FAILED_TEST_STOPPED_A_PUBLISH: Final = (
    "a check an author wrote and that failed stopped a publish"
)
A_SYSTEM_CHECK_DID_NOT_STOP_A_PUBLISH: Final = (
    "a check the system wrote and that failed did not stop a publish"
)
AN_AUTHOR_S_CHECK_CAN_BE_RAISED: Final = "a check an author wrote carries a field that raises it"

#: A module that holds a tool catalogue and calls a model, as a second loop would be written.
PROBE: Final = (
    "from brain.gate.catalogue import ProjectedCatalogue\n"
    "\n"
    "\n"
    "async def second_loop(model, messages):\n"
    "    return await model.complete(messages)\n"
)
PROBE_NAME: Final = "brain.acceptance_probe_second_loop"


@check(
    leaves=("M13.7.1",),
    sentence=(
        "Read from the product's own source as deployed, no module other than the agent runtime "
        "calls a model while holding a tool catalogue, the modules that call one with no tools "
        "hold none, and a module written to do both is named by the same scan."
    ),
)
async def only_the_runtime_gives_a_model_tools(h: Harness) -> None:
    import brain
    from brain.ops import runtime_scan

    del h
    root = Path(brain.__file__).resolve().parent
    trees = runtime_scan.parsed(root)
    if len(trees) < runtime_scan.AT_LEAST_THIS_MANY_MODULES:
        raise CheckNotRunError(NO_SOURCE_HERE)
    if runtime_scan.findings(trees):
        raise CheckFailedError(A_SECOND_RUNTIME_EXISTS)
    probed = runtime_scan.findings({**trees, PROBE_NAME: ast.parse(PROBE)})
    if not any(one.startswith(f"{PROBE_NAME}:") for one in probed):
        raise CheckFailedError(THE_SCAN_CANNOT_SAY_NO)


@check(
    leaves=("M20.4.2",),
    sentence=(
        "Asked through the publish gate this install runs, a check an author wrote that failed "
        "leaves the publish allowed and is still reported, a check the system wrote that failed "
        "stops it, and a check an author wrote has no field that could raise it."
    ),
)
async def an_authors_failed_test_never_stops_a_publish(h: Harness) -> None:
    from brain.builder.publish import (
        Check,
        CheckOrigin,
        blocking_failures,
        decide,
        promotion_shaped_fields,
    )
    from brain.core.entitlement import EntitlementSet
    from brain.gate.injection import AutonomyTier

    reach = EntitlementSet(principal_id=h.principal(A, "author"))
    authors = Check(name="the author's own question", origin=CheckOrigin.AUTHOR, passed=False)
    system = Check(name="the system's own question", origin=CheckOrigin.SYSTEM, passed=False)

    def decided(*checks: Check) -> bool:
        return decide(
            agent_id="acceptance_agent",
            current_rung=AutonomyTier.SHADOW,
            before_ceiling=reach,
            after_ceiling=reach,
            checks=checks,
            now=h.now,
        ).may_publish

    if not decided(authors):
        raise CheckFailedError(AN_AUTHOR_S_FAILED_TEST_STOPPED_A_PUBLISH)
    if blocking_failures((authors,)) or authors.blocks:
        raise CheckFailedError(AN_AUTHOR_S_FAILED_TEST_STOPPED_A_PUBLISH)
    if decided(system, authors) or blocking_failures((authors, system)) != (system.name,):
        raise CheckFailedError(A_SYSTEM_CHECK_DID_NOT_STOP_A_PUBLISH)
    if promotion_shaped_fields(Check):
        raise CheckFailedError(AN_AUTHOR_S_CHECK_CAN_BE_RAISED)
