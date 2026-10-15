"""The install acceptance check for starting an agent from a description (M20.5.3).

`brain.agent_describe_routes` makes a draft and asks the co-author for what a person described, and
this drives it as a reserved builder of acceptance_a, through its own route function and the
install's own executor, with a stand-in answering where a provider would, as
`brain.ops.acceptance_checks_coauthor` does and for the reason it gives. An install keeping text on
its own hardware plans no stand-in, so there the check says it was not run. The template signing key
is the check's own, and everything is written inside the check's transaction and rolled back.

**What it holds, in order.** With the switch off the route is absent and no draft is made. With it
on, describing makes a draft that holds exactly one revision and none of what the model said, and
answers with the persona and the summary as suggestions, a change to what an agent may reach dropped
and the parts that are not drafted named in words; and taking the persona alone through the
co-author's own take writes the one revision that holds it.

**The switch is set explicitly off before it is set on,** whatever the install left it as, and both
are rolled back with the rest.

Task ids: M20.5.3
"""

from __future__ import annotations

import secrets
from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_builder import _builder
from brain.ops.acceptance_checks_coauthor import (
    AFTER,
    SUMMARY,
    CoauthorStandIn,
    _body,
    _revisions,
)
from brain.ops.acceptance_checks_templates import _asking, _gallery, _request
from brain.ops.acceptance_models import STAND_IN
from brain.ops.acceptance_routing import ANSWERS, stand_in_drivers, step
from brain.ops.acceptance_run import SET_UP_REACH, Harness

A, _ = RESERVED_DEPARTMENTS

#: Where this module's check stands on the Install page, after the co-author's own. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 404

MADE_WHILE_OFF: Final = "a description made a draft or reached the model while its switch was off"
NOT_STARTED: Final = "a description did not start a draft with one revision of its own"
NOT_SUGGESTED: Final = "a description was not answered with the persona and the summary suggested"
REACH_SUGGESTED: Final = "a description was answered with a change to what an agent may reach"
APPLIED_UNTAKEN: Final = "a described draft held what the model said before its author took it"
NOT_SAID: Final = "a description's answer did not say what was not drafted"
NOT_TAKEN: Final = "the persona a described draft's author took did not become the next revision"

DESCRIPTION: Final = "An agent that answers questions about an acceptance check, briefly."


@check(
    leaves=("M20.5.3",),
    sentence=(
        "A builder of acceptance_a describes an agent: with the switch off nothing is made and no "
        "model is asked; with it on they get a draft of their own at one revision, the persona and "
        "the summary suggested and none of what an agent may reach, and the persona they take "
        "becomes the draft's next revision."
    ),
)
async def describing_an_agent_starts_a_draft_and_applies_nothing(
    h: Harness,
) -> None:
    """The routes read the request's trace id from the logging context, so the check binds its own
    for the length of the run and leaves nothing bound after it."""
    import structlog

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        await _held(h)


async def _held(h: Harness) -> None:
    from brain.agent_coauthor_routes import (
        HunkSent,
        SuggestionTaken,
        take_suggestions,
    )
    from brain.agent_describe_routes import DescribeAsked, describe_an_agent
    from brain.core.errors import Absent
    from brain.models.routing import DEFAULT_TIER
    from brain.ops.acceptance_models import askable, models_for, pinned
    from brain.ops.acceptance_routing import constrained
    from brain.ops.features import switch
    from brain.ops.features_declared.agent_describe import DESCRIBE_AN_AGENT
    from brain.tables.audit import attributed_to

    await h.found_departments()
    await constrained(h, ())
    responder = CoauthorStandIn()
    models = await models_for(h, standing=stand_in_drivers(h, responder))
    askable(await models.calls.planned(), STAND_IN)
    await pinned(h, (step(ANSWERS, tier=DEFAULT_TIER),))

    builder = await _builder(h, "describer")
    app = _gallery(h, secrets.token_hex(32))
    app.state.models = models
    asking = await _asking(h, builder)

    async def switched(on: bool) -> None:
        async with h.sessions() as session:
            for statement in attributed_to(
                actor_id=builder, ent_hash=SET_UP_REACH, trace_id=h.trace_id
            ):
                await session.execute(statement)
            await switch(session, DESCRIBE_AN_AGENT, on=on, by=builder)
            await session.commit()

    asked = DescribeAsked(description=DESCRIPTION)

    await switched(False)
    asked_before = sum(responder.asked.values())
    try:
        await describe_an_agent(_request(app), asked, asking)
    except Absent:
        pass
    else:
        raise CheckFailedError(MADE_WHILE_OFF)
    if sum(responder.asked.values()) != asked_before:
        raise CheckFailedError(MADE_WHILE_OFF)

    await switched(True)
    answered = await describe_an_agent(_request(app), asked, asking)
    body: dict[str, Any] = _body(answered)
    suggestion = body.get("suggestion") or {}
    held = await _revisions(h, str(body.get("draft_id", "")))
    if answered.status_code != 201 or len(held) != 1 or body.get("revision") != 1:
        raise CheckFailedError(NOT_STARTED)
    paths = {one["path"] for one in suggestion.get("hunks", [])}
    if paths != {"persona", "identity.summary"}:
        raise CheckFailedError(NOT_SUGGESTED)
    if any(one["path"] == "authority.capabilities" for one in suggestion["hunks"]) or not any(
        one["path"] == "authority.capabilities" for one in suggestion["dropped"]
    ):
        raise CheckFailedError(REACH_SUGGESTED)
    if held[0].get("persona") == AFTER or held[0].get("identity", {}).get("summary") == SUMMARY:
        raise CheckFailedError(APPLIED_UNTAKEN)
    if not body.get("not_drafted"):
        raise CheckFailedError(NOT_SAID)

    taken = await take_suggestions(
        _request(app),
        body["draft_id"],
        SuggestionTaken(
            revision=suggestion["revision"],
            base_digest=suggestion["base_digest"],
            hunks=[
                HunkSent(path=one["path"], before=one["before"], after=one["after"])
                for one in suggestion["hunks"]
            ],
            take=["persona"],
        ),
        asking,
    )
    after = await _revisions(h, body["draft_id"])
    if taken.status_code != 200 or len(after) != 2 or after[-1].get("persona") != AFTER:
        raise CheckFailedError(NOT_TAKEN)
