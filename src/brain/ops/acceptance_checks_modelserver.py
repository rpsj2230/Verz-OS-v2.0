"""The install's checks for the model server it has switched on.

`brain.ops.overlays` starts the server where `INSTALL_SERVICES` names `modelserver` and the
server has room for it, and a container that started proves nothing about the memory design this
product sells to the owner: that it holds what the install chose and no more. So these ask, from the
worker, what a person with a shell on the server would ask.

**A server this install has not switched on is not run, never failed.** An install that chose not
to run one, or whose server had no room for it, has not got it wrong, and a red row there would
teach an owner to ignore the page. Each reason is one literal sentence (`brain.ops.acceptance`): a
reason is served on a public page, so it cannot be built from anything the check read.

**The limit is judged on what the server's docker said, and the parts on what the server itself
says.** Whether a container runs, is healthy and is held to a memory limit is invisible from inside
the worker, so the deploy step asks docker after it starts the services and keeps the answer for the
release (`brain.ops.overlays`, `THE_SERVER_REPORTS_WHAT_RUNS_AND_THE_CHECK_READS_IT`); the first
check reads it and compares the limit with the one this install's own settings cost, which is not a
constant in this file. The second asks the server's readiness route, which lists the parts it was
told to run and every file or program one of them is missing, and which loads nothing.
**Rejected: loading a part to prove it works.** That would hold the memory the check is there to
show is given back, and a check that cost the install what it measures is a check nobody can run
beside the work.

**What these do not prove, and the leaves that wait for something else.** That a document is read
and a passage is embedded is proved by the checks of the parts that do it, and that a measured peak
reaches the database is proved by the check that sends the server a batch; neither is here. Nothing
here claims a leaf closed: they are evidence that the frame is the one that was costed.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import structlog

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.ops.overlays import Seen

#: Where this module's checks stand on the Install page, before every larger key.
CHECK_ORDER: Final = 396

log = structlog.get_logger(__name__)

#: How long the readiness route may take. It reads the disk and answers; it loads nothing.
READY_TIMEOUT_SECONDS: Final = 10.0

#: Said where the install has not switched the model server on.
NO_MODEL_SERVER_HERE: Final = (
    "this install has not switched the model server on: INSTALL_SERVICES does not name modelserver"
)

#: Said where the deploy step has not reported this release's optional services.
NOT_REPORTED_FOR_THIS_RELEASE: Final = (
    "the deploy step has not reported this release's optional services yet, so there is nothing "
    "the server said to judge; it reports them after every deploy that starts them"
)

#: Said where the server's docker does not show the model server running and healthy.
THE_MODEL_SERVER_IS_NOT_RUNNING: Final = (
    "the model server is not running and healthy on this release as the server reported it"
)

#: Said where it runs under a limit other than the one this install's settings cost.
THE_MODEL_SERVER_IS_NOT_HELD_TO_ITS_LIMIT: Final = (
    "the model server runs under a memory limit other than the one this install's settings cost; "
    "the worker's log gives both figures"
)

#: Said where the settings cannot be read as a configuration at all.
THE_SETTINGS_CANNOT_BE_READ: Final = (
    "the model server's settings on this install are not a configuration it could have started "
    "with, so there is no limit to compare the running one with"
)

#: Said where the server does not answer its readiness route from the worker.
THE_MODEL_SERVER_DID_NOT_ANSWER: Final = (
    "the model server this install has switched on did not answer its readiness route from the "
    "worker"
)

#: Said where it answers that it is not ready.
A_PART_IS_NOT_READY: Final = (
    "the model server says a part this install chose is missing what it needs to load; the "
    "worker's log names which"
)

#: Said where it answers ready for a set of parts other than the ones this install chose.
IT_RUNS_OTHER_PARTS_THAN_WERE_CHOSEN: Final = (
    "the model server reports running a set of parts other than the one this install chose, so "
    "the memory it was costed for is not the memory it may take"
)


async def _reported(h: Harness) -> dict[str, Seen]:
    """What the deploy step reported of the services for this release, or not run."""
    from brain.ops.overlays import BY_NAME, OBSERVED_KEY, seen_in, switched_on_here
    from brain.ops.setting_store import read_namespace

    if BY_NAME["modelserver"] not in switched_on_here():
        raise CheckNotRunError(NO_MODEL_SERVER_HERE)
    namespace = OBSERVED_KEY.split(".", 1)[0]
    async with h.sessions() as session:
        held = await read_namespace(session, namespace)
    row = held.get(OBSERVED_KEY)
    seen = None if row is None else seen_in(row.value, commit=h.settings.resolved_commit())
    if seen is None:
        raise CheckNotRunError(NOT_REPORTED_FOR_THIS_RELEASE)
    return dict(seen)


@check(
    leaves=("M7.3.3",),
    sentence=(
        "The model server this install has switched on runs and is reported healthy by the "
        "server's own docker on this release, under a memory limit equal to the one this "
        "install's own settings cost, so it cannot take memory the plan did not give it."
    ),
)
async def the_model_server_runs_under_the_limit_this_install_costed(h: Harness) -> None:
    from brain.ops.model_server import ModelServerError, effective_limit_mib, read_config
    from brain.ops.wiring import component

    seen = await _reported(h)
    name = component("inference-server").name
    one = seen.get(name)
    if one is None or (one.state, one.health) != ("running", "healthy"):
        raise CheckFailedError(THE_MODEL_SERVER_IS_NOT_RUNNING)
    try:
        wanted = effective_limit_mib(read_config())
    except ModelServerError as error:
        raise CheckFailedError(THE_SETTINGS_CANNOT_BE_READ) from error
    log.info("acceptance.model_server_limit", costed_mib=wanted, running_mib=one.limit_mib)
    if one.limit_mib != wanted:
        raise CheckFailedError(THE_MODEL_SERVER_IS_NOT_HELD_TO_ITS_LIMIT)


@check(
    leaves=("M7.3.3",),
    sentence=(
        "The model server this install has switched on says, from the worker, that every part "
        "this install chose has its weights and its libraries and that it runs those parts and "
        "no others, without loading any of them."
    ),
)
async def the_model_server_reports_ready_for_exactly_the_parts_chosen(h: Harness) -> None:
    import httpx

    from brain.knowledge.embed_policy import embedding_endpoint
    from brain.ops.model_server import ModelServerError, read_config
    from brain.ops.overlays import BY_NAME, switched_on_here

    if BY_NAME["modelserver"] not in switched_on_here():
        raise CheckNotRunError(NO_MODEL_SERVER_HERE)
    try:
        chosen = {one.value for one in read_config().parts}
    except ModelServerError as error:
        raise CheckFailedError(THE_SETTINGS_CANNOT_BE_READ) from error
    try:
        async with httpx.AsyncClient(timeout=READY_TIMEOUT_SECONDS) as client:
            answer = await client.get(f"{embedding_endpoint().rstrip('/')}/ready")
            body = answer.json()
            status = answer.status_code
    except (httpx.HTTPError, ValueError) as error:
        raise CheckFailedError(THE_MODEL_SERVER_DID_NOT_ANSWER) from error
    if not isinstance(body, dict):
        raise CheckFailedError(THE_MODEL_SERVER_DID_NOT_ANSWER)
    gaps = body.get("gaps")
    log.info(
        "acceptance.model_server_ready",
        status=status,
        gaps=[str(one) for one in gaps] if isinstance(gaps, list) else [],
    )
    if status != 200 or body.get("ready") is not True:
        raise CheckFailedError(A_PART_IS_NOT_READY)
    parts = body.get("parts")
    if not isinstance(parts, list) or {str(one) for one in parts} != chosen:
        raise CheckFailedError(IT_RUNS_OTHER_PARTS_THAN_WERE_CHOSEN)
